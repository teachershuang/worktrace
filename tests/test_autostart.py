from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from worktrace.runtime.autostart import AutostartManager, quote_windows_arg


class AutostartManagerTests(unittest.TestCase):
    def test_enable_and_disable_manage_startup_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.yaml"
            config_path.write_text("{}", encoding="utf-8")
            startup_dir = root / "startup"

            manager = AutostartManager(config_path=config_path, startup_dir=startup_dir)
            status = manager.enable()

            self.assertTrue(status.supported)
            self.assertTrue(status.enabled)
            startup_file = startup_dir / "WorkTrace.cmd"
            self.assertTrue(startup_file.exists())

            script = startup_file.read_text(encoding="utf-8")
            self.assertIn("tray", script)
            self.assertIn(str(config_path), script)

            disabled = manager.disable()
            self.assertTrue(disabled.supported)
            self.assertFalse(disabled.enabled)
            self.assertFalse(startup_file.exists())

    def test_quote_windows_arg_wraps_spaced_values(self) -> None:
        self.assertEqual(quote_windows_arg(r"C:\WorkTrace"), r"C:\WorkTrace")
        self.assertEqual(quote_windows_arg(r"C:\Program Files\WorkTrace"), r'"C:\Program Files\WorkTrace"')


if __name__ == "__main__":
    unittest.main()
