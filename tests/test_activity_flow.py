from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from worktrace.capture.screen import ActiveWindow, ScreenSnapshot
from worktrace.classifier.activity import (
    ActivityClassifier,
    ActivityDecision,
    ClassificationContext,
)
from worktrace.ocr.client import OCRResult
from worktrace.runtime.recorder import WorkRecorder
from worktrace.runtime.state import RuntimeStateStore
from worktrace.timeline.store import EventStore


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def chat_json(self, *_args, **_kwargs):
        return self.payload


class FakeCapture:
    def __init__(self, captured_at: datetime):
        self.captured_at = captured_at

    def capture_primary(self) -> ScreenSnapshot:
        return ScreenSnapshot(
            captured_at=self.captured_at,
            image_png=b"png",
            active_window=ActiveWindow(app_name="browser.exe", title="需求评审"),
        )


class FakeOCR:
    def recognize_png(self, _image_bytes: bytes) -> OCRResult:
        return OCRResult(text="客户需求 接口 调试", raw={"text": "客户需求 接口 调试"})


class FakeClassifier:
    def __init__(self, decision: ActivityDecision):
        self.decision = decision

    def classify(self, _context):
        return self.decision


class ActivityFlowTests(unittest.TestCase):
    def test_low_confidence_result_is_forced_to_review(self) -> None:
        classifier = ActivityClassifier(
            FakeLLM(
                {
                    "should_record": False,
                    "is_work": False,
                    "category": "其他",
                    "project": None,
                    "title": "无法判断",
                    "summary": "当前内容不足以判断是否为工作",
                    "confidence": 0.42,
                    "need_review": False,
                    "skip_reason": "信息不足",
                }
            )
        )
        context = ClassificationContext(
            captured_at=datetime(2026, 6, 18, 10, 0, 0),
            active_window=ActiveWindow(app_name="browser.exe", title="未知页面"),
            ocr_text="片段内容",
            previous_event=None,
            recent_summary="",
            project_names_today=[],
        )

        decision = classifier.classify(context)

        self.assertFalse(decision.should_record)
        self.assertTrue(decision.need_review)

    def test_review_event_does_not_enter_effective_timeline(self) -> None:
        captured_at = datetime(2026, 6, 18, 10, 5, 0)
        decision = ActivityDecision(
            should_record=True,
            is_work=True,
            category="开发编码",
            project="WorkTrace",
            title="调试记录流程",
            summary="调试截图 OCR 到大模型判断的记录流程",
            confidence=0.58,
            need_review=True,
            skip_reason=None,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(Path(temp_dir))
            recorder = WorkRecorder(
                capture=FakeCapture(captured_at),
                ocr=FakeOCR(),
                classifier=FakeClassifier(decision),
                store=store,
            )

            event = recorder.record_once()

            self.assertEqual(len(store.load_raw(captured_at.date())), 1)
            self.assertEqual(len(store.load_review(captured_at.date())), 1)
            self.assertEqual(len(store.load_effective(captured_at.date())), 0)
            self.assertEqual(store.load_review(captured_at.date())[0]["id"], event["id"])

    def test_start_state_clears_pause_and_stop_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStateStore(Path(temp_dir) / "runtime_state.json")

            store.pause()
            store.request_stop()
            store.start()

            state = store.load()
            self.assertFalse(state.paused)
            self.assertFalse(state.stop_requested)


if __name__ == "__main__":
    unittest.main()
