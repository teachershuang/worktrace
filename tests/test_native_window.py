from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from worktrace.ui.native import (
    DESKTOP_WINDOW_HEIGHT,
    DESKTOP_WINDOW_MIN_HEIGHT,
    DESKTOP_WINDOW_MIN_WIDTH,
    DESKTOP_WINDOW_WIDTH,
    NativeWindowLifecycle,
    image_data_uri,
    native_pet_html,
)


class NativeWindowTests(unittest.TestCase):
    def test_default_desktop_window_uses_compact_size(self) -> None:
        self.assertLessEqual(DESKTOP_WINDOW_WIDTH, 1000)
        self.assertLessEqual(DESKTOP_WINDOW_HEIGHT, 720)
        self.assertLess(DESKTOP_WINDOW_MIN_WIDTH, DESKTOP_WINDOW_WIDTH)
        self.assertLess(DESKTOP_WINDOW_MIN_HEIGHT, DESKTOP_WINDOW_HEIGHT)

    def test_close_hides_window_until_explicit_exit(self) -> None:
        window = FakeWindow()
        server = FakeServerHandle()
        lifecycle = NativeWindowLifecycle(window, server)

        self.assertFalse(lifecycle.hide_to_tray())
        self.assertEqual(window.hidden_count, 1)
        self.assertFalse(window.destroyed)
        self.assertFalse(server.stopped)

        lifecycle.exit_app()
        self.assertTrue(window.destroyed)

        lifecycle.cleanup()
        self.assertTrue(server.stopped)

    def test_close_allows_destroy_when_exiting(self) -> None:
        window = FakeWindow()
        lifecycle = NativeWindowLifecycle(window, FakeServerHandle())
        lifecycle.exiting = True

        self.assertTrue(lifecycle.hide_to_tray())
        self.assertEqual(window.hidden_count, 0)

    def test_native_pet_embeds_images_without_file_urls(self) -> None:
        html = native_pet_html()

        self.assertEqual(html.count("data:image/png;base64,"), 2)
        self.assertNotIn("file:///", html)
        self.assertIn("WorkTrace 助手", html)
        self.assertIn("助手猫咪", html)
        self.assertIn("待命中", html)

    def test_image_data_uri_reports_missing_asset(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.png"
            with self.assertRaisesRegex(RuntimeError, "desktop pet asset unavailable"):
                image_data_uri(missing)


class FakeWindow:
    def __init__(self) -> None:
        self.hidden_count = 0
        self.shown_count = 0
        self.restored_count = 0
        self.destroyed = False

    def hide(self) -> None:
        self.hidden_count += 1

    def show(self) -> None:
        self.shown_count += 1

    def restore(self) -> None:
        self.restored_count += 1

    def destroy(self) -> None:
        self.destroyed = True


class FakeServerHandle:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


if __name__ == "__main__":
    unittest.main()
