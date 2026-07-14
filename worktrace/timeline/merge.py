from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class TimelineItem:
    start_at: datetime
    end_at: datetime
    project: str | None
    category: str
    title: str
    summary: str
    source_event_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_at": self.start_at.isoformat(timespec="seconds"),
            "end_at": self.end_at.isoformat(timespec="seconds"),
            "project": self.project,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "source_event_ids": self.source_event_ids,
        }

    def display_line(self) -> str:
        return f"{self.start_at:%H:%M} - {self.end_at:%H:%M}  {self.title}"


def merge_events(events: list[dict[str, Any]], max_gap_minutes: int = 30) -> list[TimelineItem]:
    sorted_events = sorted(events, key=lambda item: item.get("captured_at", ""))
    items: list[TimelineItem] = []
    for event in sorted_events:
        item = event_to_timeline_item(event)
        if item is None:
            continue
        if items and can_merge(items[-1], item, max_gap_minutes=max_gap_minutes):
            merge_into(items[-1], item)
        else:
            items.append(item)
    return items


def event_to_timeline_item(event: dict[str, Any]) -> TimelineItem | None:
    captured_at = parse_time(event.get("captured_at"))
    if captured_at is None:
        return None
    classification = event.get("classification", {})
    title = str(classification.get("title") or "未命名工作事件")
    summary = str(classification.get("summary") or title)
    return TimelineItem(
        start_at=captured_at,
        end_at=captured_at,
        project=classification.get("project"),
        category=str(classification.get("category") or "其他"),
        title=title,
        summary=summary,
        source_event_ids=[str(event.get("id") or "")],
    )


def can_merge(previous: TimelineItem, current: TimelineItem, max_gap_minutes: int) -> bool:
    if current.start_at - previous.end_at > timedelta(minutes=max_gap_minutes):
        return False
    if previous.project != current.project:
        return False
    if previous.category != current.category:
        return False
    return text_similarity(previous.summary, current.summary) >= 0.22 or previous.title == current.title


def merge_into(previous: TimelineItem, current: TimelineItem) -> None:
    previous.end_at = current.end_at
    previous.source_event_ids.extend(current.source_event_ids)
    if text_similarity(previous.summary, current.summary) < 0.75:
        previous.summary = f"{previous.summary}；{current.summary}"
    if len(current.title) > len(previous.title) and text_similarity(previous.title, current.title) >= 0.5:
        previous.title = current.title


def text_similarity(left: str, right: str) -> float:
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(overlap) / len(union)


def tokenize(text: str) -> set[str]:
    compact = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    if any("\u4e00" <= ch <= "\u9fff" for ch in compact):
        joined = "".join(compact.split())
        return {joined[index : index + 2] for index in range(max(len(joined) - 1, 0))}
    words = {word for word in compact.split() if len(word) >= 2}
    if words:
        return words
    return {text[index : index + 2] for index in range(max(len(text) - 1, 0))}


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
