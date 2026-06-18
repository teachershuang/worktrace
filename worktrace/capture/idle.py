from __future__ import annotations

import ctypes
import logging
import platform
from ctypes import wintypes

logger = logging.getLogger(__name__)


def get_idle_seconds() -> float | None:
    if platform.system() != "Windows":
        return None
    try:
        return _get_windows_idle_seconds()
    except Exception:
        logger.exception("failed to read system idle time")
        return None


class _LastInputInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


def _get_windows_idle_seconds() -> float:
    last_input = _LastInputInfo()
    last_input.cbSize = ctypes.sizeof(_LastInputInfo)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input)):
        raise ctypes.WinError()
    tick_count = ctypes.windll.kernel32.GetTickCount()
    elapsed_ms = tick_count - last_input.dwTime
    return max(elapsed_ms / 1000.0, 0.0)
