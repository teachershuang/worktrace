from __future__ import annotations

import unittest

from worktrace.ui.native import (
    DESKTOP_WINDOW_HEIGHT,
    DESKTOP_WINDOW_MIN_HEIGHT,
    DESKTOP_WINDOW_MIN_WIDTH,
    DESKTOP_WINDOW_WIDTH,
)


class NativeWindowTests(unittest.TestCase):
    def test_default_desktop_window_uses_compact_size(self) -> None:
        self.assertLessEqual(DESKTOP_WINDOW_WIDTH, 1000)
        self.assertLessEqual(DESKTOP_WINDOW_HEIGHT, 720)
        self.assertLess(DESKTOP_WINDOW_MIN_WIDTH, DESKTOP_WINDOW_WIDTH)
        self.assertLess(DESKTOP_WINDOW_MIN_HEIGHT, DESKTOP_WINDOW_HEIGHT)


if __name__ == "__main__":
    unittest.main()
