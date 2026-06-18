from __future__ import annotations

import logging
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from worktrace.ui.api import create_app, latest_report_path


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
            daily_path.write_text("# 今日日报\n\n一、今日完成工作", encoding="utf-8")

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
                self.assertEqual(payload["content"], "# 今日日报\n\n一、今日完成工作")
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


if __name__ == "__main__":
    unittest.main()
