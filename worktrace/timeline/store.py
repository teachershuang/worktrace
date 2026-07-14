from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventPaths:
    raw: Path
    effective: Path
    review: Path


class EventStore:
    def __init__(self, data_dir: Path):
        self.events_dir = data_dir / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def paths_for(self, day: date) -> EventPaths:
        prefix = day.isoformat()
        return EventPaths(
            raw=self.events_dir / f"{prefix}.raw.jsonl",
            effective=self.events_dir / f"{prefix}.effective.jsonl",
            review=self.events_dir / f"{prefix}.review.jsonl",
        )

    def append_raw(self, event: dict[str, Any], day: date | None = None) -> dict[str, Any]:
        item = with_event_id(event)
        with self._lock:
            self._append_unlocked(self.paths_for(day or datetime.now().date()).raw, item)
        return item

    def append_effective(self, event: dict[str, Any], day: date | None = None) -> dict[str, Any]:
        item = with_event_id(event)
        with self._lock:
            self._append_unlocked(self.paths_for(day or datetime.now().date()).effective, item)
        return item

    def append_review(self, event: dict[str, Any], day: date | None = None) -> dict[str, Any]:
        item = with_event_id(event)
        with self._lock:
            self._append_unlocked(self.paths_for(day or datetime.now().date()).review, item)
        return item

    def load_raw(self, day: date) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_jsonl_unlocked(self.paths_for(day).raw)

    def load_effective(self, day: date) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_jsonl_unlocked(self.paths_for(day).effective)

    def load_review(self, day: date) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_jsonl_unlocked(self.paths_for(day).review)

    def replace_review(self, day: date, items: Iterable[dict[str, Any]]) -> None:
        with self._lock:
            self._replace_jsonl_unlocked(self.paths_for(day).review, items)

    def resolve_reviews(self, day: date, id_prefixes: list[str], *, as_work: bool) -> list[dict[str, Any]]:
        with self._lock:
            items = self._read_jsonl_unlocked(self.paths_for(day).review)
            selected, remaining = split_by_id_prefix(items, id_prefixes)
            resolved = [resolved_review_event(item, as_work=as_work) for item in selected]
            if as_work:
                for item in resolved:
                    self._append_unlocked(self.paths_for(day).effective, item)
            self._replace_jsonl_unlocked(self.paths_for(day).review, remaining)
            return resolved

    def resolve_review_item(self, day: date, event_id_prefix: str, *, as_work: bool) -> dict[str, Any]:
        with self._lock:
            items = self._read_jsonl_unlocked(self.paths_for(day).review)
            matches = [item for item in items if str(item.get("id", "")).startswith(event_id_prefix)]
            if not matches:
                raise LookupError(event_id_prefix)
            if len(matches) > 1:
                raise ValueError(event_id_prefix)
            selected = matches[0]
            remaining = [item for item in items if item.get("id") != selected.get("id")]
            resolved = resolved_review_event(selected, as_work=as_work)
            if as_work:
                self._append_unlocked(self.paths_for(day).effective, resolved)
            self._replace_jsonl_unlocked(self.paths_for(day).review, remaining)
            return resolved

    def load_effective_between(self, start: date, end: date) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        current = start
        while current <= end:
            items.extend(self.load_effective(current))
            current += timedelta(days=1)
        return items

    @staticmethod
    def _append_unlocked(path: Path, event: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def _replace_jsonl_unlocked(path: Path, items: Iterable[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            for item in items:
                file.write(json.dumps(item, ensure_ascii=False) + "\n")
        temporary_path.replace(path)

    @staticmethod
    def _read_jsonl_unlocked(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        items = []
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                line = line.strip()
                if line:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("skipping malformed event line: %s:%s", path, line_number)
                        continue
                    if isinstance(item, dict):
                        items.append(item)
        return items


def with_event_id(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("id"):
        return event
    copied = dict(event)
    copied["id"] = uuid4().hex
    return copied


def split_by_id_prefix(
    items: list[dict[str, Any]], id_prefixes: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not id_prefixes:
        return items, []
    selected = []
    remaining = []
    for item in items:
        event_id = str(item.get("id", ""))
        (selected if any(event_id.startswith(prefix) for prefix in id_prefixes) else remaining).append(item)
    return selected, remaining


def resolved_review_event(event: dict[str, Any], *, as_work: bool) -> dict[str, Any]:
    copied = dict(event)
    classification = dict(copied.get("classification", {}))
    classification["should_record"] = as_work
    classification["is_work"] = as_work
    classification["need_review"] = False
    classification["skip_reason"] = None if as_work else "用户确认为非工作"
    copied["classification"] = classification
    return copied
