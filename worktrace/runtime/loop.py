from __future__ import annotations

import logging
import time
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
    ):
        self.settings = settings
        self.recorder = recorder
        self.state_store = state_store
        self.periods = settings.recording.parsed_periods()

    def run_forever(self) -> None:
        self.state_store.start()
        logger.info("WorkTrace background recorder started")
        while True:
            state = self.state_store.load()
            now = datetime.now()
            in_work_period = is_within_work_periods(now, self.periods)
            status = LoopStatus(
                paused=state.paused,
                in_work_period=in_work_period,
                stop_requested=state.stop_requested,
            )
            if status.stop_requested:
                logger.info("WorkTrace background recorder stopped by state request")
                return

            if status.paused:
                logger.info("recording paused")
                self._sleep_short()
                continue

            if not status.in_work_period:
                logger.info("outside configured work periods, skipping")
                self._sleep_short()
                continue

            idle_seconds = get_idle_seconds()
            idle_limit_seconds = self.settings.recording.idle_skip_minutes * 60
            if idle_limit_seconds > 0 and idle_seconds is not None and idle_seconds >= idle_limit_seconds:
                logger.info("system idle for %.0fs, skipping record cycle", idle_seconds)
                self._sleep_short()
                continue

            try:
                self.recorder.record_once()
            except Exception:
                logger.exception("record cycle failed")

            time.sleep(self.settings.recording.screenshot_interval_seconds)

    @staticmethod
    def _sleep_short() -> None:
        time.sleep(30)
