"""Single-instance guard: named per-user mutex.

A second copy (installed build + dev run, or an accidental double
launch) would fight the first over the global hotkey hook. The second
instance tells the user the app is already in the tray and exits.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys

log = logging.getLogger(__name__)

_MUTEX_NAME = "Local\\ParrotypeSingleInstance"
_ERROR_ALREADY_EXISTS = 183
_mutex_handle = None      # keep alive for the process lifetime


def acquire() -> bool:
    """True when this is the first instance (mutex acquired)."""
    if sys.platform != "win32":
        return True
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _mutex_handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    return kernel32.GetLastError() != _ERROR_ALREADY_EXISTS


def notify_already_running(title: str, body: str) -> None:
    """Native MessageBox (no Qt needed); suppressible for headless tests."""
    if os.environ.get("PARROTYPE_SUPPRESS_SINGLETON_UI"):
        return
    MB_ICONINFORMATION = 0x40
    ctypes.windll.user32.MessageBoxW(None, body, title, MB_ICONINFORMATION)
