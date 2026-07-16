"""Native Windows chrome helpers (dark titlebar via DWM)."""

from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19   # pre-20H1 builds


def enable_dark_titlebar(widget) -> None:  # noqa: ANN001
    """Ask DWM to draw a dark titlebar for the given top-level QWidget."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        value = ctypes.c_int(1)
        for attr in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                return
        log.debug("DwmSetWindowAttribute dark mode not supported")
    except Exception as exc:
        log.debug("Dark titlebar failed: %s", exc)
