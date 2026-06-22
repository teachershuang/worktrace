from __future__ import annotations

import json
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageTk

STATIC_ASSETS = Path(__file__).resolve().parent / "static" / "assets"
TRANSPARENT_COLOR = "#ff00ff"


@dataclass(frozen=True)
class DesktopPetPreferences:
    x: int = 32
    y: int = 180


@dataclass(frozen=True)
class DesktopPetView:
    asset_name: str
    badge_text: str
    badge_fill: str
    badge_text_fill: str
    asset_size: int


class DesktopPetPreferencesStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> DesktopPetPreferences:
        if not self.path.exists():
            return DesktopPetPreferences()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return DesktopPetPreferences()
        return DesktopPetPreferences(
            x=int(payload.get("x", DesktopPetPreferences.x)),
            y=int(payload.get("y", DesktopPetPreferences.y)),
        )

    def save(self, prefs: DesktopPetPreferences) -> None:
        self.path.write_text(
            json.dumps({"x": prefs.x, "y": prefs.y}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def select_pet_view(
    *,
    loop_running: bool,
    paused: bool,
    review_count: int,
    in_work_period: bool,
) -> DesktopPetView:
    if paused:
        return DesktopPetView(
            asset_name="assistant-rest.png",
            badge_text="暂停中",
            badge_fill="#FFF0C9",
            badge_text_fill="#8C6200",
            asset_size=116,
        )
    if review_count > 0:
        return DesktopPetView(
            asset_name="assistant-sidebar.png",
            badge_text=f"待确认 {review_count}",
            badge_fill="#FFE5E3",
            badge_text_fill="#B23A32",
            asset_size=112,
        )
    if loop_running and in_work_period:
        return DesktopPetView(
            asset_name="assistant-main.png",
            badge_text="记录中",
            badge_fill="#DCF0DF",
            badge_text_fill="#2D7A3D",
            asset_size=120,
        )
    if in_work_period:
        return DesktopPetView(
            asset_name="assistant-sidebar.png",
            badge_text="待命中",
            badge_fill="#E8F0FB",
            badge_text_fill="#3D6EA8",
            asset_size=112,
        )
    return DesktopPetView(
        asset_name="assistant-rest.png",
        badge_text="休息中",
        badge_fill="#EFE7DC",
        badge_text_fill="#726659",
        asset_size=116,
    )


class DesktopPetWindow:
    def __init__(
        self,
        *,
        data_dir: Path,
        fetch_view: Callable[[], DesktopPetView],
        open_console: Callable[[], None],
        on_quit: Callable[[], None],
    ):
        self.fetch_view = fetch_view
        self.open_console = open_console
        self.on_quit = on_quit
        self.preferences_store = DesktopPetPreferencesStore(data_dir / "desktop_pet.json")
        self.preferences = self.preferences_store.load()

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_COLOR)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)

        self.canvas = tk.Canvas(
            self.root,
            width=168,
            height=168,
            bg=TRANSPARENT_COLOR,
            bd=0,
            highlightthickness=0,
            relief="flat",
        )
        self.canvas.pack()

        self._photo: ImageTk.PhotoImage | None = None
        self._drag_origin: tuple[int, int] | None = None
        self._window_origin: tuple[int, int] | None = None
        self._drag_moved = False
        self._after_id: str | None = None
        self._closed = False

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right_click)

        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label="打开控制台", command=self._menu_open_console)
        self.menu.add_command(label="退出 WorkTrace", command=self._menu_quit)

    def run(self) -> None:
        self.root.geometry(f"+{self.preferences.x}+{self.preferences.y}")
        self.root.deiconify()
        self.refresh()
        self.root.mainloop()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        try:
            self.root.destroy()
        except tk.TclError:
            return

    def refresh(self) -> None:
        if self._closed:
            return
        view = self.fetch_view()
        self._render(view)
        self._after_id = self.root.after(2500, self.refresh)

    def _render(self, view: DesktopPetView) -> None:
        asset_path = STATIC_ASSETS / "mascot" / view.asset_name
        image = Image.open(asset_path).convert("RGBA")
        image.thumbnail((view.asset_size, view.asset_size), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image)

        self.canvas.delete("all")
        self.canvas.create_image(84, 58, image=self._photo)
        self._draw_badge(
            text=view.badge_text,
            fill=view.badge_fill,
            text_fill=view.badge_text_fill,
            x=84,
            y=140,
        )

    def _draw_badge(self, *, text: str, fill: str, text_fill: str, x: int, y: int) -> None:
        width = max(78, 24 + len(text) * 12)
        height = 28
        left = x - width // 2
        top = y - height // 2
        right = left + width
        bottom = top + height
        radius = 14

        self.canvas.create_rectangle(left + radius, top, right - radius, bottom, fill=fill, outline="")
        self.canvas.create_rectangle(left, top + radius, right, bottom - radius, fill=fill, outline="")
        self.canvas.create_oval(left, top, left + radius * 2, bottom, fill=fill, outline="")
        self.canvas.create_oval(right - radius * 2, top, right, bottom, fill=fill, outline="")
        self.canvas.create_text(
            x,
            y,
            text=text,
            fill=text_fill,
            font=("Microsoft YaHei UI", 10, "bold"),
        )

    def _on_press(self, event) -> None:
        self._drag_origin = (event.x_root, event.y_root)
        self._window_origin = (self.root.winfo_x(), self.root.winfo_y())
        self._drag_moved = False

    def _on_drag(self, event) -> None:
        if not self._drag_origin or not self._window_origin:
            return
        dx = event.x_root - self._drag_origin[0]
        dy = event.y_root - self._drag_origin[1]
        if abs(dx) > 3 or abs(dy) > 3:
            self._drag_moved = True
        self.root.geometry(f"+{self._window_origin[0] + dx}+{self._window_origin[1] + dy}")

    def _on_release(self, _event) -> None:
        if self._drag_moved:
            self.preferences = DesktopPetPreferences(x=self.root.winfo_x(), y=self.root.winfo_y())
            self.preferences_store.save(self.preferences)
        else:
            self.open_console()
        self._drag_origin = None
        self._window_origin = None

    def _on_right_click(self, event) -> None:
        self.menu.tk_popup(event.x_root, event.y_root)

    def _menu_open_console(self) -> None:
        self.open_console()

    def _menu_quit(self) -> None:
        self.on_quit()
