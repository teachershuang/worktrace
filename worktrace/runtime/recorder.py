from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from worktrace.capture.screen import CaptureError, ScreenCapture
from worktrace.classifier.activity import (
    ActivityClassifier,
    ClassificationContext,
    context_to_dict,
    decision_to_dict,
)
from worktrace.ocr.client import OCRClient, OCRError
from worktrace.timeline.store import EventStore

logger = logging.getLogger(__name__)


class WorkRecorder:
    def __init__(
        self,
        capture: ScreenCapture,
        ocr: OCRClient,
        classifier: ActivityClassifier,
        store: EventStore,
    ):
        self.capture = capture
        self.ocr = ocr
        self.classifier = classifier
        self.store = store
        self.consecutive_ocr_failures = 0

    def record_once(self) -> dict[str, Any]:
        try:
            snapshot = self.capture.capture_primary()
        except CaptureError as exc:
            logger.error("record skipped because capture failed: %s", exc)
            raise

        ocr_text = ""
        ocr_raw: dict[str, Any] = {}
        ocr_error: str | None = None
        try:
            ocr_result = self.ocr.recognize_png(snapshot.image_png)
            ocr_text = ocr_result.text
            ocr_raw = ocr_result.raw
            self.consecutive_ocr_failures = 0
        except OCRError as exc:
            ocr_error = str(exc)
            self.consecutive_ocr_failures += 1
            logger.warning("OCR failed, falling back to window metadata: %s", exc)

        now = snapshot.captured_at
        context = ClassificationContext(
            captured_at=now,
            active_window=snapshot.active_window,
            ocr_text=ocr_text,
            ocr_error=ocr_error,
            previous_event=self._previous_valid_event(now),
            recent_summary=self._recent_summary(now),
            project_names_today=self._project_names_today(now),
        )
        decision = self.classifier.classify(context)

        event = {
            "captured_at": now.isoformat(timespec="seconds"),
            "active_window": {
                "app_name": snapshot.active_window.app_name,
                "title": snapshot.active_window.title,
            },
            "ocr": {
                "text": ocr_text,
                "raw": ocr_raw,
                "error": ocr_error,
                "consecutive_failures": self.consecutive_ocr_failures,
            },
            "classification": decision_to_dict(decision),
            "context": context_to_dict(context),
        }

        raw_event = self.store.append_raw(event, now.date())
        if decision.need_review:
            self.store.append_review(raw_event, now.date())
        if decision.should_record:
            self.store.append_effective(raw_event, now.date())

        logger.info(
            "recorded event should_record=%s need_review=%s confidence=%.2f title=%s",
            decision.should_record,
            decision.need_review,
            decision.confidence,
            decision.title,
        )
        return raw_event

    def _previous_valid_event(self, now: datetime) -> dict[str, Any] | None:
        events = self.store.load_effective(now.date())
        return events[-1] if events else None

    def _recent_summary(self, now: datetime) -> str:
        cutoff = now - timedelta(minutes=30)
        parts = []
        for event in self.store.load_effective(now.date()):
            captured_at = parse_event_time(event)
            if captured_at and captured_at >= cutoff:
                classification = event.get("classification", {})
                title = classification.get("title")
                summary = classification.get("summary")
                if title or summary:
                    parts.append(f"{title}: {summary}")
        return "\n".join(parts[-8:])

    def _project_names_today(self, now: datetime) -> list[str]:
        projects = []
        for event in self.store.load_effective(now.date()):
            project = event.get("classification", {}).get("project")
            if project and project not in projects:
                projects.append(project)
        return projects


def parse_event_time(event: dict[str, Any]) -> datetime | None:
    value = event.get("captured_at")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
