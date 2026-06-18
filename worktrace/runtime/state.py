from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeState:
    paused: bool = False
    stop_requested: bool = False


class RuntimeStateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState()
        try:
            data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return RuntimeState()
        return RuntimeState(
            paused=bool(data.get("paused", False)),
            stop_requested=bool(data.get("stop_requested", False)),
        )

    def save(self, state: RuntimeState) -> None:
        self.path.write_text(
            json.dumps(state.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def pause(self) -> None:
        current = self.load()
        self.save(RuntimeState(paused=True, stop_requested=current.stop_requested))

    def resume(self) -> None:
        current = self.load()
        self.save(RuntimeState(paused=False, stop_requested=current.stop_requested))

    def start(self) -> None:
        self.save(RuntimeState(paused=False, stop_requested=False))

    def request_stop(self) -> None:
        current = self.load()
        self.save(RuntimeState(paused=current.paused, stop_requested=True))

    def clear_stop(self) -> None:
        current = self.load()
        self.save(RuntimeState(paused=current.paused, stop_requested=False))
