from __future__ import annotations

import ctypes
import logging
import platform
from dataclasses import dataclass

from worktrace.capture.screen import ActiveWindow, get_active_window
from worktrace.config.settings import RecordingSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForegroundDecision:
    skip: bool
    reason: str | None
    screen_locked: bool
    fullscreen: bool
    active_window: ActiveWindow


def evaluate_foreground(settings: RecordingSettings) -> ForegroundDecision:
    if platform.system() != "Windows":
        return ForegroundDecision(False, None, False, False, ActiveWindow(None, None))

    active_window = get_active_window()
    screen_locked = is_windows_session_locked(active_window)
    fullscreen = is_foreground_fullscreen()
    return decide_foreground(
        settings,
        active_window=active_window,
        screen_locked=screen_locked,
        fullscreen=fullscreen,
    )


def decide_foreground(
    settings: RecordingSettings,
    *,
    active_window: ActiveWindow,
    screen_locked: bool,
    fullscreen: bool,
) -> ForegroundDecision:
    app_name = (active_window.app_name or "").casefold()
    title = (active_window.title or "").strip().casefold()

    if settings.skip_when_screen_locked and screen_locked:
        return ForegroundDecision(True, "Windows 已锁屏，已跳过截图", True, fullscreen, active_window)

    if settings.skip_own_windows and is_worktrace_window(app_name, title):
        return ForegroundDecision(True, "WorkTrace 窗口位于前台，已跳过自身记录", False, fullscreen, active_window)

    fullscreen_apps = {name.strip().casefold() for name in settings.fullscreen_skip_apps if name.strip()}
    if fullscreen and app_name in fullscreen_apps:
        return ForegroundDecision(
            True,
            f"{active_window.app_name or '指定程序'} 正在全屏运行，已按配置跳过截图",
            False,
            True,
            active_window,
        )

    return ForegroundDecision(False, None, screen_locked, fullscreen, active_window)


def is_worktrace_window(app_name: str, title: str) -> bool:
    if app_name in {"worktrace.exe", "worktrace-cli.exe"}:
        return True
    return title in {"worktrace", "worktrace pet", "worktrace 本地控制台"}


def is_windows_session_locked(active_window: ActiveWindow | None = None) -> bool:
    if (active_window and (active_window.app_name or "").casefold() == "logonui.exe"):
        return True

    desktop_switch = 0x0100
    user32 = ctypes.windll.user32
    desktop = user32.OpenInputDesktop(0, False, desktop_switch)
    if not desktop:
        return False
    try:
        return not bool(user32.SwitchDesktop(desktop))
    finally:
        user32.CloseDesktop(desktop)


def is_foreground_fullscreen(tolerance: int = 2) -> bool:
    try:
        import win32api
        import win32gui

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd or win32gui.IsIconic(hwnd):
            return False
        window_rect = win32gui.GetWindowRect(hwnd)
        monitor = win32api.MonitorFromWindow(hwnd, 2)
        monitor_rect = win32api.GetMonitorInfo(monitor)["Monitor"]
        return all(abs(left - right) <= tolerance for left, right in zip(window_rect, monitor_rect))
    except Exception:
        logger.debug("failed to inspect foreground fullscreen state", exc_info=True)
        return False
