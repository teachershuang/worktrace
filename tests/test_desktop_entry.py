from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from worktrace.ui.cli import default_desktop_config_path


class DesktopEntryTests(unittest.TestCase):
    def test_default_desktop_config_prefers_real_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            try:
                (root / "config.example.yaml").write_text("{}", encoding="utf-8")
                (root / "config.lan.example.yaml").write_text("{}", encoding="utf-8")
                (root / "config.yaml").write_text("{}", encoding="utf-8")
                import os

                os.chdir(root)
                self.assertEqual(default_desktop_config_path(), Path("config.yaml"))
            finally:
                import os

                os.chdir(original_cwd)

    def test_default_desktop_config_falls_back_to_examples(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            try:
                (root / "config.lan.example.yaml").write_text("{}", encoding="utf-8")
                import os

                os.chdir(root)
                self.assertEqual(default_desktop_config_path(), Path("config.lan.example.yaml"))
            finally:
                import os

                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
