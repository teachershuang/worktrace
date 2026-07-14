from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from worktrace.capture.foreground import ForegroundDecision, decide_foreground
from worktrace.capture.screen import ActiveWindow
from worktrace.config.settings import AppSettings, LLMSettings, OCRSettings, RecordingSettings, StorageSettings
from worktrace.runtime.loop import BackgroundRecorderLoop
from worktrace.runtime.state import RuntimeStateStore


class ForegroundGuardTests(unittest.TestCase):
    def test_locked_screen_is_skipped_before_capture(self) -> None:
        decision = decide_foreground(
            RecordingSettings(),
            active_window=ActiveWindow("LogonUI.exe", "Windows Default Lock Screen"),
            screen_locked=True,
            fullscreen=True,
        )

        self.assertTrue(decision.skip)
        self.assertIn("锁屏", decision.reason or "")

    def test_worktrace_window_is_not_recorded_as_work(self) -> None:
        decision = decide_foreground(
            RecordingSettings(),
            active_window=ActiveWindow("WorkTrace.exe", "WorkTrace"),
            screen_locked=False,
            fullscreen=False,
        )

        self.assertTrue(decision.skip)
        self.assertIn("自身记录", decision.reason or "")

    def test_fullscreen_skip_only_applies_to_configured_apps(self) -> None:
        settings = RecordingSettings(fullscreen_skip_apps=["vlc.exe"])

        skipped = decide_foreground(
            settings,
            active_window=ActiveWindow("VLC.EXE", "Video"),
            screen_locked=False,
            fullscreen=True,
        )
        allowed = decide_foreground(
            settings,
            active_window=ActiveWindow("Code.exe", "main.py"),
            screen_locked=False,
            fullscreen=True,
        )

        self.assertTrue(skipped.skip)
        self.assertFalse(allowed.skip)

    def test_background_loop_marks_foreground_skip_without_recording(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = AppSettings(
                llm=LLMSettings(base_url="http://127.0.0.1/v1", model="test"),
                ocr=OCRSettings(url="http://127.0.0.1/ocr"),
                recording=RecordingSettings(
                    work_periods=["00:00-23:59"],
                    short_poll_interval_seconds=1,
                    idle_skip_minutes=0,
                ),
                storage=StorageSettings(data_dir=root, report_output_dir=root / "reports", log_dir=root / "logs"),
            )
            state_store = RuntimeStateStore(root / "runtime_state.json")
            stop_event = threading.Event()
            recorder = FailingRecorder()
            loop = BackgroundRecorderLoop(settings, recorder, state_store, stop_event=stop_event)
            loop._sleep = lambda _seconds: stop_event.set()
            decision = ForegroundDecision(
                skip=True,
                reason="WorkTrace 窗口位于前台，已跳过自身记录",
                screen_locked=False,
                fullscreen=False,
                active_window=ActiveWindow("WorkTrace.exe", "WorkTrace"),
            )

            with patch("worktrace.runtime.loop.evaluate_foreground", return_value=decision):
                loop.run_forever()

            self.assertFalse(recorder.called)
            self.assertEqual(state_store.load().last_activity_status, "skipped")
            self.assertIn("自身记录", state_store.load().last_activity_reason or "")


class FailingRecorder:
    def __init__(self) -> None:
        self.called = False

    def record_once(self) -> None:
        self.called = True
        raise AssertionError("foreground guard should skip before recorder is called")


if __name__ == "__main__":
    unittest.main()
