from __future__ import annotations

import io
import logging
import platform
from dataclasses import dataclass
from datetime import datetime

import mss
from PIL import Image

logger = logging.getLogger(__name__)


class CaptureError(RuntimeError):
    """Raised when screen capture fails."""


@dataclass(frozen=True)
class ActiveWindow:
    app_name: str | None
    title: str | None


@dataclass(frozen=True)
class ScreenSnapshot:
    captured_at: datetime
    image_png: bytes
    active_window: ActiveWindow


class ScreenCapture:
    def capture_primary(self) -> ScreenSnapshot:
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                raw = sct.grab(monitor)
                image = Image.frombytes("RGB", raw.size, raw.rgb)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
        except Exception as exc:
            logger.exception("screen capture failed")
            raise CaptureError(f"screen capture failed: {exc}") from exc

        return ScreenSnapshot(
            captured_at=datetime.now(),
            image_png=buffer.getvalue(),
            active_window=get_active_window(),
        )


def get_active_window() -> ActiveWindow:
    if platform.system() != "Windows":
        return ActiveWindow(app_name=None, title=None)

    try:
        import win32gui
        import win32process
        import psutil

        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) or None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        app_name = psutil.Process(pid).name()
        return ActiveWindow(app_name=app_name, title=title)
    except Exception:
        logger.exception("failed to read active window metadata")
        return ActiveWindow(app_name=None, title=None)
