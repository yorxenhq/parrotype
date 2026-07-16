"""Native Windows chrome helpers (dark titlebar via DWM)."""

from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19   # pre-20H1 builds
_DWMWA_CAPTION_COLOR = 35                 # Win11 22000+
_DWMWA_TEXT_COLOR = 36

_CAPTION_COLORREF = 0x001C1717            # #17171C as 0x00BBGGRR
_TEXT_COLORREF = 0x00F1ECEC               # #ECECF1 as 0x00BBGGRR


def enable_dark_titlebar(widget) -> None:  # noqa: ANN001
    """Force the design-token titlebar on a top-level QWidget.

    Explicit caption/text colors beat the user's accent color ("show
    accent on title bars" paints captions red/blue otherwise — the
    dark-mode attribute alone does not override it). On builds older
    than Win11 22000 the color attributes are unsupported, so the
    dark-mode attribute stays as the fallback.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1)
        dark_ok = False
        for attr in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                dark_ok = True
                break
        caption = ctypes.c_uint(_CAPTION_COLORREF)
        text = ctypes.c_uint(_TEXT_COLORREF)
        color_ok = dwm.DwmSetWindowAttribute(
            hwnd, _DWMWA_CAPTION_COLOR, ctypes.byref(caption), ctypes.sizeof(caption)
        ) == 0
        if color_ok:
            dwm.DwmSetWindowAttribute(
                hwnd, _DWMWA_TEXT_COLOR, ctypes.byref(text), ctypes.sizeof(text)
            )
        if not (dark_ok or color_ok):
            log.debug("DWM titlebar customization not supported on this build")
    except Exception as exc:
        log.debug("Dark titlebar failed: %s", exc)
