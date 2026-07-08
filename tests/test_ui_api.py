from __future__ import annotations

import logging
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from worktrace.llm.client import LLMError
from worktrace.timeline.store import EventStore
from worktrace.ui.api import create_app, describe_runtime_error, latest_report_path


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
            finally:
                logging.shutdown()

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

                response = client.put("/api/config/editable", json=current)

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["saved"])
                saved = config_path.read_text(encoding="utf-8")
                self.assertIn("http://192.168.8.29:4000/v1", saved)
                self.assertIn("paddle_json", saved)
                self.assertIn("screenshot_interval_seconds: 120", saved)
                summary = client.get("/api/config/summary").json()
                self.assertEqual(summary["llm"]["base_url"], "http://192.168.8.29:4000/v1")
                self.assertEqual(summary["ocr"]["url"], "http://192.168.8.29:8866/ocr")
                self.assertEqual(summary["recording"]["screenshot_interval_seconds"], 120)
            finally:
                logging.shutdown()


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


if __name__ == "__main__":
    unittest.main()
