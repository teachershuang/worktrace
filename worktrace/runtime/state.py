from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeState:
    paused: bool = False
    stop_requested: bool = False
    last_activity_at: str | None = None
    last_activity_status: str | None = None
    last_activity_reason: str | None = None
    last_event_id: str | None = None


class RuntimeStateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def load(self) -> RuntimeState:
        with self._lock:
            return self._load_unlocked()

    def _load_unlocked(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState()
        try:
            data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return RuntimeState()
        return RuntimeState(
            paused=bool(data.get("paused", False)),
            stop_requested=bool(data.get("stop_requested", False)),
            last_activity_at=optional_str(data.get("last_activity_at")),
            last_activity_status=optional_str(data.get("last_activity_status")),
            last_activity_reason=optional_str(data.get("last_activity_reason")),
            last_event_id=optional_str(data.get("last_event_id")),
        )

    def save(self, state: RuntimeState) -> None:
        with self._lock:
            self._save_unlocked(state)

    def _save_unlocked(self, state: RuntimeState) -> None:
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(state.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)

    def pause(self) -> None:
        with self._lock:
            current = self._load_unlocked()
            self._save_unlocked(with_state_flags(current, paused=True, stop_requested=current.stop_requested))

    def resume(self) -> None:
        with self._lock:
            current = self._load_unlocked()
            self._save_unlocked(with_state_flags(current, paused=False, stop_requested=current.stop_requested))

    def start(self) -> None:
        with self._lock:
            current = self._load_unlocked()
            self._save_unlocked(with_state_flags(current, paused=False, stop_requested=False))

    def request_stop(self) -> None:
        with self._lock:
            current = self._load_unlocked()
            self._save_unlocked(with_state_flags(current, paused=current.paused, stop_requested=True))

    def clear_stop(self) -> None:
        with self._lock:
            current = self._load_unlocked()
            self._save_unlocked(with_state_flags(current, paused=current.paused, stop_requested=False))

    def mark_activity(
        self,
        *,
        status: str,
        reason: str,
        occurred_at: str,
        event_id: str | None = None,
    ) -> None:
        with self._lock:
            current = self._load_unlocked()
            self._save_unlocked(
                RuntimeState(
                    paused=current.paused,
                    stop_requested=current.stop_requested,
                    last_activity_at=occurred_at,
                    last_activity_status=status,
                    last_activity_reason=reason,
                    last_event_id=event_id,
                )
            )


def optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def with_state_flags(current: RuntimeState, *, paused: bool, stop_requested: bool) -> RuntimeState:
    return RuntimeState(
        paused=paused,
        stop_requested=stop_requested,
        last_activity_at=current.last_activity_at,
        last_activity_status=current.last_activity_status,
        last_activity_reason=current.last_activity_reason,
        last_event_id=current.last_event_id,
    )
