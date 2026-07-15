from __future__ import annotations

import unittest

from worktrace.ui.native import (
    DESKTOP_WINDOW_HEIGHT,
    DESKTOP_WINDOW_MIN_HEIGHT,
    DESKTOP_WINDOW_MIN_WIDTH,
    DESKTOP_WINDOW_WIDTH,
    PET_COLLAPSED_SIZE,
    PET_EXPANDED_SIZE,
    NativePetBridge,
    NativeWindowLifecycle,
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

    def test_native_pet_bridge_resizes_and_opens_console(self) -> None:
        window = FakeWindow()
        pet_window = FakeWindow()
        lifecycle = NativeWindowLifecycle(window, FakeServerHandle(), pet_window=pet_window)
        bridge = NativePetBridge()
        bridge.bind(lifecycle, pet_window)

        self.assertTrue(all(name.startswith("_") for name in vars(bridge)))

        self.assertEqual(
            bridge.set_expanded(True),
            {"expanded": True, "width": PET_EXPANDED_SIZE[0], "height": PET_EXPANDED_SIZE[1]},
        )
        self.assertEqual(pet_window.sizes[-1], PET_EXPANDED_SIZE)

        self.assertTrue(bridge.show_console())
        self.assertEqual(window.shown_count, 1)
        self.assertEqual(window.restored_count, 1)

        bridge.set_expanded(False)
        self.assertEqual(pet_window.sizes[-1], PET_COLLAPSED_SIZE)


class FakeWindow:
    def __init__(self) -> None:
        self.hidden_count = 0
        self.shown_count = 0
        self.restored_count = 0
        self.destroyed = False
        self.sizes: list[tuple[int, int]] = []

    def hide(self) -> None:
        self.hidden_count += 1

    def show(self) -> None:
        self.shown_count += 1

    def restore(self) -> None:
        self.restored_count += 1

    def destroy(self) -> None:
        self.destroyed = True

    def resize(self, width: int, height: int) -> None:
        self.sizes.append((width, height))


class FakeServerHandle:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


if __name__ == "__main__":
    unittest.main()
