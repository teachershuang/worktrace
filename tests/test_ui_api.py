from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from worktrace.llm.client import LLMError
from worktrace.timeline.store import EventStore
from worktrace.runtime.state import RuntimeState, RuntimeStateStore
from worktrace.ui.api import (
    ConsoleRuntime,
    create_app,
    describe_runtime_error,
    latest_report_path,
    pet_state_payload,
    service_alert_payload,
)


class ConsoleApiTests(unittest.TestCase):
    def test_latest_report_path_matches_report_generator_names(self) -> None:
        output_dir = Path("data/reports")
        now = datetime(2026, 6, 18, 15, 30)

        self.assertEqual(
            latest_report_path(output_dir, "daily", now),
            output_dir / "2026-06-18-daily.md",
        )
        self.assertEqual(
            latest_report_path(output_dir, "weekly", now),
            output_dir / "2026-06-15_to_2026-06-21-weekly.md",
        )
        self.assertIsNone(latest_report_path(output_dir, "monthly", now))

    def test_latest_report_endpoint_reads_existing_daily_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.yaml"
            reports_dir = root / "reports"
            daily_path = latest_report_path(reports_dir, "daily", datetime.now())
            assert daily_path is not None
            daily_path.parent.mkdir(parents=True, exist_ok=True)
            daily_path.write_text("# Daily Report\n\n1. Finish API", encoding="utf-8")

            config_path.write_text(
                f"""
llm:
  base_url: "http://127.0.0.1:8000/v1"
  api_key: "test"
  model: "test-model"
ocr:
  url: "http://127.0.0.1:9000/ocr"
storage:
  data_dir: "{(root / "data").as_posix()}"
  report_output_dir: "{reports_dir.as_posix()}"
  log_dir: "{(root / "logs").as_posix()}"
""".strip(),
                encoding="utf-8",
            )

            try:
                client = TestClient(create_app(config_path))
                response = client.get("/api/reports/latest/daily")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["exists"])
                self.assertEqual(payload["content"], "# Daily Report\n\n1. Finish API")
            finally:
                logging.shutdown()

    def test_config_summary_exposes_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = write_test_config(root)

            try:
                client = TestClient(create_app(config_path))
                response = client.get("/api/config/summary")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["llm"]["model"], "test-model")
                self.assertEqual(payload["ocr"]["protocol"], "multipart")
                self.assertEqual(payload["storage"]["data_dir"], str(root / "data"))
                self.assertIn("desktop", payload)
            finally:
                logging.shutdown()

    def test_daily_report_empty_state_returns_user_facing_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = write_test_config(root)

            try:
                client = TestClient(create_app(config_path))
                response = client.post("/api/reports/daily")

                self.assertEqual(response.status_code, 500)
                self.assertIn("今天还没有可用于生成日报", response.json()["detail"])
            finally:
                logging.shutdown()

    def test_autostart_endpoint_reflects_temp_startup_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = write_test_config(root)
            startup_root = root / "Roaming"
            original_appdata = os.environ.get("APPDATA")
            os.environ["APPDATA"] = str(startup_root)

            try:
                client = TestClient(create_app(config_path))
                response = client.get("/api/autostart")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["supported"])
                self.assertFalse(payload["enabled"])
                self.assertTrue(payload["startup_file"].endswith("WorkTrace.cmd"))
            finally:
                if original_appdata is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = original_appdata
                logging.shutdown()

    def test_save_latest_report_updates_markdown_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = write_test_config(root)

            try:
                client = TestClient(create_app(config_path))
                response = client.put("/api/reports/latest/daily", json={"content": "# Manual Daily Report"})

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["saved"])
                self.assertEqual(Path(payload["path"]).read_text(encoding="utf-8"), "# Manual Daily Report")
            finally:
                logging.shutdown()

    def test_bulk_review_work_moves_selected_items_to_effective(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = write_test_config(root)
            store = EventStore(root / "data")
            today = datetime.now().date()
            first = store.append_review(make_review_event("alpha"), today)
            second = store.append_review(make_review_event("beta"), today)

            try:
                client = TestClient(create_app(config_path))
                response = client.post("/api/review/bulk/work", json={"ids": [first["id"]], "date": today.isoformat()})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["count"], 1)
                effective = store.load_effective(today)
                review = store.load_review(today)
                self.assertEqual([item["id"] for item in effective], [first["id"]])
                self.assertEqual([item["id"] for item in review], [second["id"]])
            finally:
                logging.shutdown()

    def test_single_review_action_uses_selected_history_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = write_test_config(root)
            store = EventStore(root / "data")
            history_day = datetime.now().date().replace(day=1)
            review = store.append_review(make_review_event("history"), history_day)

            try:
                client = TestClient(create_app(config_path))
                response = client.post(
                    f"/api/review/{review['id']}/work",
                    params={"day": history_day.isoformat()},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["date"], history_day.isoformat())
                self.assertEqual(store.load_review(history_day), [])
                self.assertEqual(store.load_effective(history_day)[0]["id"], review["id"])
            finally:
                logging.shutdown()

    def test_diagnostics_endpoint_reports_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = write_test_config(root)

            try:
                client = TestClient(create_app(config_path))
                response = client.get("/api/diagnostics")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("ocr", payload)
                self.assertIn("llm", payload)
                self.assertIn("storage", payload)
                self.assertIn("last_activity", payload)
                self.assertEqual(payload["events"]["effective_today"], 0)
            finally:
                logging.shutdown()

    def test_describe_runtime_error_hides_llm_401_details(self) -> None:
        message = describe_runtime_error(
            LLMError("LLM request failed: Client error '401 Unauthorized' for url 'http://127.0.0.1:4000/v1/chat/completions'")
        )
        self.assertIn("LLM 服务认证失败", message)
        self.assertNotIn("chat/completions", message)


    def test_status_endpoint_reports_last_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = write_test_config(root)

            try:
                client = TestClient(create_app(config_path))
                response = client.get("/api/status")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("last_activity", payload)
                self.assertEqual(
                    sorted(payload["last_activity"].keys()),
                    ["at", "event_id", "reason", "status"],
                )
                self.assertEqual(payload["review_count"], 0)
                self.assertFalse(payload["service_alert"]["active"])
                self.assertEqual(payload["pet_state"]["kind"], "standby")
            finally:
                logging.shutdown()

    def test_desktop_pet_endpoint_serves_dynamic_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = write_test_config(Path(temp_dir))
            try:
                client = TestClient(create_app(config_path))
                response = client.get("/desktop-pet")

                self.assertEqual(response.status_code, 200)
                self.assertIn("WorkTrace Pet", response.text)
                self.assertIn("/static/pet.js", response.text)
                self.assertIn("开始 / 恢复", response.text)
            finally:
                logging.shutdown()

    def test_pet_state_prioritizes_service_error_pause_and_review(self) -> None:
        alert = service_alert_payload(
            RuntimeState(),
            ocr_consecutive_failures=2,
            service_checks={"ocr": None, "llm": None},
        )
        self.assertEqual(alert["service"], "ocr")
        self.assertEqual(
            pet_state_payload(
                loop_running=True,
                paused=True,
                in_work_period=True,
                review_count=3,
                service_alert=alert,
            )["kind"],
            "error",
        )
        self.assertEqual(
            pet_state_payload(
                loop_running=True,
                paused=True,
                in_work_period=True,
                review_count=3,
                service_alert={"active": False},
            )["kind"],
            "paused",
        )
        self.assertEqual(
            pet_state_payload(
                loop_running=True,
                paused=False,
                in_work_period=True,
                review_count=3,
                service_alert={"active": False},
            )["kind"],
            "review",
        )

    def test_editable_config_can_update_service_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = write_test_config(root)

            try:
                client = TestClient(create_app(config_path))
                current = client.get("/api/config/editable").json()
                current["llm"]["base_url"] = "http://192.168.8.29:4000/v1"
                current["llm"]["model"] = "Qwen3.6-35B-A3B-GGUF"
                current["ocr"]["url"] = "http://192.168.8.29:8866/ocr"
                current["ocr"]["protocol"] = "paddle_json"
                current["recording"]["work_periods"] = "09:00-12:00,13:30-18:00"
                current["recording"]["screenshot_interval_seconds"] = 120
                current["recording"]["short_poll_interval_seconds"] = 3
                current["recording"]["fullscreen_skip_apps"] = "vlc.exe,game.exe"

                response = client.put("/api/config/editable", json=current)

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["saved"])
                saved = config_path.read_text(encoding="utf-8")
                self.assertIn("http://192.168.8.29:4000/v1", saved)
                self.assertIn("paddle_json", saved)
                self.assertIn("screenshot_interval_seconds: 120", saved)
                self.assertIn("short_poll_interval_seconds: 3", saved)
                self.assertIn("vlc.exe", saved)
                summary = client.get("/api/config/summary").json()
                self.assertEqual(summary["llm"]["base_url"], "http://192.168.8.29:4000/v1")
                self.assertEqual(summary["ocr"]["url"], "http://192.168.8.29:8866/ocr")
                self.assertEqual(summary["recording"]["screenshot_interval_seconds"], 120)
                self.assertEqual(summary["recording"]["short_poll_interval_seconds"], 3)
                self.assertEqual(summary["recording"]["fullscreen_skip_apps"], ["vlc.exe", "game.exe"])
            finally:
                logging.shutdown()

    def test_console_runtime_stop_interrupts_sleeping_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_store = RuntimeStateStore(Path(temp_dir) / "runtime_state.json")
            context = SimpleNamespace(settings=object(), recorder=object(), state_store=state_store)
            runtime = ConsoleRuntime(context)

            with patch("worktrace.ui.api.BackgroundRecorderLoop", InterruptibleFakeLoop):
                self.assertTrue(runtime.start_loop())
                started_at = time.perf_counter()
                self.assertTrue(runtime.stop_loop(timeout=1.0))

            self.assertLess(time.perf_counter() - started_at, 0.5)
            self.assertFalse(runtime.loop_running())

    def test_console_runtime_restarts_loop_after_context_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_state = RuntimeStateStore(Path(first_dir) / "runtime_state.json")
            second_state = RuntimeStateStore(Path(second_dir) / "runtime_state.json")
            first_context = SimpleNamespace(settings=object(), recorder=object(), state_store=first_state)
            second_context = SimpleNamespace(settings=object(), recorder=object(), state_store=second_state)
            runtime = ConsoleRuntime(first_context)

            with patch("worktrace.ui.api.BackgroundRecorderLoop", InterruptibleFakeLoop):
                runtime.start_loop()
                first_state.pause()
                restarted = runtime.replace_context(second_context)
                self.assertTrue(restarted)
                self.assertTrue(runtime.loop_running())
                self.assertTrue(second_state.load().paused)
                runtime.stop_loop(timeout=1.0)


def write_test_config(root: Path) -> Path:
    config_path = root / "config.yaml"
    config_path.write_text(
        f"""
llm:
  base_url: "http://127.0.0.1:8000/v1"
  api_key: "test"
  model: "test-model"
ocr:
  url: "http://127.0.0.1:9000/ocr"
storage:
  data_dir: "{(root / "data").as_posix()}"
  report_output_dir: "{(root / "reports").as_posix()}"
  log_dir: "{(root / "logs").as_posix()}"
""".strip(),
        encoding="utf-8",
    )
    return config_path


def make_review_event(title: str) -> dict:
    return {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "app_name": "TestApp",
        "window_title": "Test Window",
        "classification": {
            "should_record": False,
            "is_work": True,
            "category": "Other",
            "project": "WorkTrace",
            "title": title,
            "summary": f"{title} summary",
            "confidence": 0.52,
            "need_review": True,
            "skip_reason": None,
        },
    }


class InterruptibleFakeLoop:
    def __init__(self, _settings, _recorder, _state_store, stop_event: threading.Event):
        self.stop_event = stop_event

    def run_forever(self) -> None:
        self.stop_event.wait(30)


if __name__ == "__main__":
    unittest.main()
