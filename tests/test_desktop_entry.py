from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

from typer.testing import CliRunner

from worktrace import __version__
from worktrace.ui.cli import app, default_desktop_config_path


class DesktopEntryTests(unittest.TestCase):
    def test_cli_exposes_version(self) -> None:
        result = CliRunner().invoke(app, ["--version"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn(f"WorkTrace {__version__}", result.stdout)

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
                self.assertEqual(default_desktop_config_path(), (root / "config.yaml").resolve())
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
                self.assertEqual(default_desktop_config_path(), (root / "config.lan.example.yaml").resolve())
            finally:
                import os

                os.chdir(original_cwd)

    def test_frozen_desktop_materializes_editable_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            internal = root / "_internal"
            internal.mkdir()
            source = internal / "config.example.yaml"
            source.write_text("llm:\n  base_url: http://127.0.0.1:8000/v1\n", encoding="utf-8")

            original_executable = sys.executable
            original_frozen = getattr(sys, "frozen", None)
            try:
                sys.executable = str(root / "WorkTrace.exe")
                sys.frozen = True

                result = default_desktop_config_path()

                self.assertEqual(result, (root / "config.yaml").resolve())
                self.assertEqual(result.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            finally:
                sys.executable = original_executable
                if original_frozen is None:
                    delattr(sys, "frozen")
                else:
                    sys.frozen = original_frozen


if __name__ == "__main__":
    unittest.main()
