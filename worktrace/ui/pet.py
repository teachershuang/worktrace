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


@dataclass(frozen=True)
class DesktopPetStatus:
    view: DesktopPetView
    loop_running: bool
    paused: bool
    review_count: int
    in_work_period: bool
    last_activity_status: str | None = None
    last_activity_reason: str | None = None
    last_activity_at: str | None = None

    @property
    def headline(self) -> str:
        if self.paused:
            return "已暂停"
        if self.loop_running:
            return "后台记录中"
        if self.in_work_period:
            return "工作时段待命"
        return "休息时段"

    @property
    def detail(self) -> str:
        review = f"{self.review_count} 条待确认" if self.review_count else "暂无待确认"
        period = "工作时段内" if self.in_work_period else "非工作时段"
        return f"{period} · {review}"

    @property
    def last_activity_summary(self) -> str:
        if not self.last_activity_status:
            return "最近活动：尚未记录"
        label = {
            "recorded": "已记录",
            "review": "待确认",
            "skipped": "已跳过",
            "paused": "已暂停",
            "failed": "记录失败",
        }.get(self.last_activity_status, self.last_activity_status)
        reason = self.last_activity_reason or "无详细原因"
        at = self.last_activity_at[11:16] if self.last_activity_at and len(self.last_activity_at) >= 16 else "--:--"
        return f"{at} {label}：{reason}"


@dataclass(frozen=True)
class DesktopPetActions:
    start_recording: Callable[[], None]
    pause_recording: Callable[[], None]
    resume_recording: Callable[[], None]
    record_once: Callable[[], None]
    generate_daily_report: Callable[[], None]
    open_console: Callable[[], None]
    quit_app: Callable[[], None]


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


def build_pet_status(
    *,
    loop_running: bool,
    paused: bool,
    review_count: int,
    in_work_period: bool,
    last_activity_status: str | None = None,
    last_activity_reason: str | None = None,
    last_activity_at: str | None = None,
) -> DesktopPetStatus:
    return DesktopPetStatus(
        view=select_pet_view(
            loop_running=loop_running,
            paused=paused,
            review_count=review_count,
            in_work_period=in_work_period,
        ),
        loop_running=loop_running,
        paused=paused,
        review_count=review_count,
        in_work_period=in_work_period,
        last_activity_status=last_activity_status,
        last_activity_reason=last_activity_reason,
        last_activity_at=last_activity_at,
    )


class DesktopPetWindow:
    def __init__(
        self,
        *,
        data_dir: Path,
        fetch_status: Callable[[], DesktopPetStatus],
        actions: DesktopPetActions,
    ):
        self.fetch_status = fetch_status
        self.actions = actions
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
        self._panel: tk.Toplevel | None = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right_click)

        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label="打开快捷面板", command=self.toggle_panel)
        self.menu.add_command(label="打开控制台", command=self.actions.open_console)
        self.menu.add_separator()
        self.menu.add_command(label="退出 WorkTrace", command=self.actions.quit_app)

    def run(self) -> None:
        self.preferences = self._visible_preferences(self.preferences)
        self.root.geometry(f"+{self.preferences.x}+{self.preferences.y}")
        self.root.deiconify()
        self.root.lift()
        self.refresh()
        self.root.mainloop()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self._destroy_panel()
        try:
            self.root.destroy()
        except tk.TclError:
            return

    def refresh(self) -> None:
        if self._closed:
            return
        status = self.fetch_status()
        self._render(status.view)
        if self._panel and self._panel.winfo_exists():
            self._render_panel(status)
        self._after_id = self.root.after(2500, self.refresh)

    def toggle_panel(self) -> None:
        if self._panel and self._panel.winfo_exists():
            self._destroy_panel()
            return
        self._panel = tk.Toplevel(self.root)
        self._panel.overrideredirect(True)
        self._panel.attributes("-topmost", True)
        self._panel.configure(bg="#FFF8EF")
        self._position_panel()
        self._render_panel(self.fetch_status())
        self._panel.bind("<FocusOut>", lambda _event: self._destroy_panel())
        self._panel.focus_force()

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

    def _render_panel(self, status: DesktopPetStatus) -> None:
        if not self._panel:
            return
        for child in self._panel.winfo_children():
            child.destroy()

        frame = tk.Frame(
            self._panel,
            bg="#FFF8EF",
            highlightbackground="#E8D3BA",
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        frame.pack(fill="both", expand=True)

        title = tk.Label(
            frame,
            text=status.headline,
            bg="#FFF8EF",
            fg="#2D241D",
            font=("Microsoft YaHei UI", 11, "bold"),
            anchor="w",
        )
        title.pack(fill="x")

        detail = tk.Label(
            frame,
            text=status.detail,
            bg="#FFF8EF",
            fg="#76695E",
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        )
        detail.pack(fill="x", pady=(2, 10))

        recent = tk.Label(
            frame,
            text=status.last_activity_summary,
            bg="#FFF8EF",
            fg="#5E5147",
            font=("Microsoft YaHei UI", 8),
            anchor="w",
            justify="left",
            wraplength=164,
        )
        recent.pack(fill="x", pady=(0, 10))

        self._add_button(frame, "开始记录", self._run_panel_action(self.actions.start_recording), disabled=status.loop_running)
        self._add_button(frame, "暂停", self._run_panel_action(self.actions.pause_recording), disabled=not status.loop_running or status.paused)
        self._add_button(frame, "恢复", self._run_panel_action(self.actions.resume_recording), disabled=not status.paused)
        self._add_button(frame, "立即记录一次", self._run_panel_action(self.actions.record_once))
        self._add_button(frame, "生成今日日报", self._run_panel_action(self.actions.generate_daily_report))
        self._add_button(frame, "打开控制台", self._run_panel_action(self.actions.open_console))
        self._add_button(frame, "退出 WorkTrace", self.actions.quit_app, danger=True)

    def _add_button(
        self,
        parent: tk.Frame,
        text: str,
        command: Callable[[], None],
        *,
        disabled: bool = False,
        danger: bool = False,
    ) -> None:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            state="disabled" if disabled else "normal",
            bg="#FFE9D2" if not danger else "#FFE2DE",
            activebackground="#F9D8B7" if not danger else "#F6C9C2",
            fg="#2D241D" if not danger else "#98352F",
            disabledforeground="#A99B8E",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=10,
            pady=6,
        )
        button.pack(fill="x", pady=(0, 6))

    def _run_panel_action(self, action: Callable[[], None]) -> Callable[[], None]:
        def run() -> None:
            action()
            self.root.after(300, self.refresh)

        return run

    def _position_panel(self) -> None:
        if not self._panel:
            return
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        panel_width = 196
        panel_height = 372
        pet_x = self.root.winfo_x()
        pet_y = self.root.winfo_y()

        x = pet_x + 142
        if x + panel_width > screen_width:
            x = max(8, pet_x - panel_width + 18)
        y = max(8, pet_y + 10)
        self._panel.geometry(f"{panel_width}x{panel_height}+{x}+{y}")

    def _visible_preferences(self, prefs: DesktopPetPreferences) -> DesktopPetPreferences:
        screen_width = max(self.root.winfo_screenwidth(), 200)
        screen_height = max(self.root.winfo_screenheight(), 200)
        max_x = max(8, screen_width - 180)
        max_y = max(8, screen_height - 190)
        x = min(max(8, prefs.x), max_x)
        y = min(max(8, prefs.y), max_y)
        if x != prefs.x or y != prefs.y:
            corrected = DesktopPetPreferences(x=x, y=y)
            self.preferences_store.save(corrected)
            return corrected
        return prefs

    def _destroy_panel(self) -> None:
        if not self._panel:
            return
        try:
            self._panel.destroy()
        except tk.TclError:
            pass
        self._panel = None

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
        if self._panel and self._panel.winfo_exists():
            self._position_panel()

    def _on_release(self, _event) -> None:
        if self._drag_moved:
            self.preferences = DesktopPetPreferences(x=self.root.winfo_x(), y=self.root.winfo_y())
            self.preferences_store.save(self.preferences)
        else:
            self.toggle_panel()
        self._drag_origin = None
        self._window_origin = None

    def _on_right_click(self, event) -> None:
        self.menu.tk_popup(event.x_root, event.y_root)
