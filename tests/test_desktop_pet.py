from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from worktrace.ui.pet import (
    DesktopPetPreferences,
    DesktopPetPreferencesStore,
    build_pet_status,
    select_pet_view,
)


class DesktopPetTests(unittest.TestCase):
    def test_pet_preferences_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DesktopPetPreferencesStore(Path(temp_dir) / "desktop_pet.json")
            store.save(DesktopPetPreferences(x=144, y=288))
            prefs = store.load()

            self.assertEqual(prefs.x, 144)
            self.assertEqual(prefs.y, 288)

    def test_select_pet_view_prefers_review_state(self) -> None:
        view = select_pet_view(
            loop_running=True,
            paused=False,
            review_count=3,
            in_work_period=True,
        )
        self.assertEqual(view.badge_text, "待确认 3")
        self.assertEqual(view.asset_name, "assistant-sidebar.png")

    def test_select_pet_view_prefers_pause_state(self) -> None:
        view = select_pet_view(
            loop_running=True,
            paused=True,
            review_count=0,
            in_work_period=True,
        )
        self.assertEqual(view.badge_text, "暂停中")
        self.assertEqual(view.asset_name, "assistant-rest.png")

    def test_build_pet_status_summarizes_current_state(self) -> None:
        status = build_pet_status(
            loop_running=True,
            paused=False,
            review_count=2,
            in_work_period=True,
        )

        self.assertEqual(status.headline, "后台记录中")
        self.assertEqual(status.detail, "工作时段内 · 2 条待确认")
        self.assertEqual(status.view.badge_text, "待确认 2")


if __name__ == "__main__":
    unittest.main()
