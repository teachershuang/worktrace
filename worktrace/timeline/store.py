from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


@dataclass(frozen=True)
class EventPaths:
    raw: Path
    effective: Path
    review: Path


class EventStore:
    def __init__(self, data_dir: Path):
        self.events_dir = data_dir / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def paths_for(self, day: date) -> EventPaths:
        prefix = day.isoformat()
        return EventPaths(
            raw=self.events_dir / f"{prefix}.raw.jsonl",
            effective=self.events_dir / f"{prefix}.effective.jsonl",
            review=self.events_dir / f"{prefix}.review.jsonl",
        )

    def append_raw(self, event: dict[str, Any], day: date | None = None) -> dict[str, Any]:
        item = with_event_id(event)
        self._append(self.paths_for(day or datetime.now().date()).raw, item)
        return item

    def append_effective(self, event: dict[str, Any], day: date | None = None) -> dict[str, Any]:
        item = with_event_id(event)
        self._append(self.paths_for(day or datetime.now().date()).effective, item)
        return item

    def append_review(self, event: dict[str, Any], day: date | None = None) -> dict[str, Any]:
        item = with_event_id(event)
        self._append(self.paths_for(day or datetime.now().date()).review, item)
        return item

    def load_raw(self, day: date) -> list[dict[str, Any]]:
        return self._read_jsonl(self.paths_for(day).raw)

    def load_effective(self, day: date) -> list[dict[str, Any]]:
        return self._read_jsonl(self.paths_for(day).effective)

    def load_review(self, day: date) -> list[dict[str, Any]]:
        return self._read_jsonl(self.paths_for(day).review)

    def replace_review(self, day: date, items: Iterable[dict[str, Any]]) -> None:
        path = self.paths_for(day).review
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            for item in items:
                file.write(json.dumps(item, ensure_ascii=False) + "\n")

    def load_effective_between(self, start: date, end: date) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        current = start
        while current <= end:
            items.extend(self.load_effective(current))
            current += timedelta(days=1)
        return items

    @staticmethod
    def _append(path: Path, event: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        items = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return items


def with_event_id(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("id"):
        return event
    copied = dict(event)
    copied["id"] = uuid4().hex
    return copied
