from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass
from datetime import datetime

from worktrace.config.settings import AppSettings
from worktrace.capture.idle import get_idle_seconds
from worktrace.runtime.recorder import WorkRecorder
from worktrace.runtime.state import RuntimeStateStore
from worktrace.runtime.time_windows import is_within_work_periods

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoopStatus:
    paused: bool
    in_work_period: bool
    stop_requested: bool


class BackgroundRecorderLoop:
    def __init__(
        self,
        settings: AppSettings,
        recorder: WorkRecorder,
        state_store: RuntimeStateStore,
        stop_event: threading.Event | None = None,
    ):
        self.settings = settings
        self.recorder = recorder
        self.state_store = state_store
        self.stop_event = stop_event or threading.Event()
        self.periods = settings.recording.parsed_periods()

    def run_forever(self) -> None:
        logger.info("WorkTrace background recorder started")
        while not self.stop_event.is_set():
            state = self.state_store.load()
            now = datetime.now()
            in_work_period = is_within_work_periods(now, self.periods)
            status = LoopStatus(
                paused=state.paused,
                in_work_period=in_work_period,
                stop_requested=state.stop_requested or self.stop_event.is_set(),
            )
            if status.stop_requested:
                logger.info("WorkTrace background recorder stopped by state request")
                return

            if status.paused:
                logger.info("recording paused")
                self._mark_loop_activity("paused", "用户已暂停记录", now)
                self._sleep_short()
                continue

            if not status.in_work_period:
                logger.info("outside configured work periods, skipping")
                self._mark_loop_activity("skipped", "当前不在配置的工作时间段内", now)
                self._sleep_short()
                continue

            idle_seconds = get_idle_seconds()
            idle_limit_seconds = self.settings.recording.idle_skip_minutes * 60
            if idle_limit_seconds > 0 and idle_seconds is not None and idle_seconds >= idle_limit_seconds:
                logger.info("system idle for %.0fs, skipping record cycle", idle_seconds)
                self._mark_loop_activity("skipped", f"系统空闲 {idle_seconds:.0f}s，已跳过截图", now)
                self._sleep_short()
                continue

            try:
                self.recorder.record_once()
            except Exception as exc:
                logger.exception("record cycle failed")
                self._mark_loop_activity("failed", f"记录周期失败：{exc}", now)

            self._sleep(self.settings.recording.screenshot_interval_seconds)

    def _sleep_short(self) -> None:
        self._sleep(self.settings.recording.short_poll_interval_seconds)

    def _sleep(self, seconds: float) -> None:
        self.stop_event.wait(seconds)

    def _mark_loop_activity(self, status: str, reason: str, occurred_at: datetime) -> None:
        self.state_store.mark_activity(
            status=status,
            reason=reason,
            occurred_at=occurred_at.isoformat(timespec="seconds"),
        )
