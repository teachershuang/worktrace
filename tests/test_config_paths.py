from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from worktrace.config.settings import load_config


class ConfigPathTests(unittest.TestCase):
    def test_relative_storage_paths_resolve_from_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "dist" / "WorkTrace"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "config.yaml"
            config_path.write_text(
                """
llm:
  base_url: "http://127.0.0.1:8000/v1"
  api_key: "test"
  model: "test-model"
ocr:
  url: "http://127.0.0.1:9000/ocr"
storage:
  data_dir: "data"
  report_output_dir: "data/reports"
  log_dir: "logs"
""".strip(),
                encoding="utf-8",
            )

            settings = load_config(config_path)

            self.assertEqual(settings.storage.data_dir, config_dir / "data")
            self.assertEqual(settings.storage.report_output_dir, config_dir / "data" / "reports")
            self.assertEqual(settings.storage.log_dir, config_dir / "logs")


if __name__ == "__main__":
    unittest.main()
