"""Guarded-injection harness for interactive e2e self-tests.

Hard rules (learned after test keystrokes leaked into the user's active
window):
  1. Never inject a single keystroke unless the foreground window is the
     test's OWN target window (verified immediately before every send).
  2. Long typing re-verifies focus between chunks (abort_check).
  3. Wait for user inactivity (GetLastInputInfo) before starting an
     interactive test; the user may grab the keyboard at any moment.
  4. Clean up your own windows afterwards.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shells.tray import wininput  # noqa: E402

user32 = ctypes.windll.user32
WM_GETTEXT, WM_GETTEXTLENGTH = 0x000D, 0x000E

# 64-bit handle hygiene: default ctypes c_int would truncate HWNDs.
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowExW.restype = ctypes.c_void_p
user32.FindWindowExW.argtypes = (
    ctypes.c_void_p, ctypes.c_void_p, ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR,
)
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetWindowThreadProcessId.argtypes = (
    ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.DWORD),
)


def window_pid(hwnd: int) -> int:
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def wait_for_user_idle(min_idle_s: float = 3.0, timeout_s: float = 180.0) -> bool:
    """Block until the user has been idle for min_idle_s. False on timeout."""
    deadline = time.monotonic() + timeout_s
    announced = False
    while time.monotonic() < deadline:
        idle = wininput.user_idle_seconds()
        if idle >= min_idle_s:
            return True
        if not announced:
            print(f"waiting for user inactivity ({idle:.1f}s idle now)…")
            announced = True
        time.sleep(0.5)
    return False


class FocusGuard:
    """Foreground-ownership check for a specific target window."""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd

    def ok(self) -> bool:
        return user32.GetForegroundWindow() == self.hwnd

    def acquire(self, attempts: int = 10) -> bool:
        """Bring the target to the foreground (no keystrokes involved)."""
        user32.ShowWindow(self.hwnd, 9)  # SW_RESTORE
        for i in range(attempts):
            if self.ok():
                return True
            user32.SetForegroundWindow(self.hwnd)
            if i >= 3:
                user32.BringWindowToTop(self.hwnd)
                _click_into(self.hwnd)
            time.sleep(0.2)
        return self.ok()

    # -- guarded injection primitives ----------------------------------

    def send_combo(self, combo: str) -> bool:
        if not self.ok():
            print(f"  ABORT: focus lost before send_combo({combo!r})")
            return False
        wininput.send_combo(combo)
        return True

    def send_key(self, vk: int, down: bool) -> bool:
        if not self.ok():
            print(f"  ABORT: focus lost before send_key({vk:#x})")
            return False
        wininput.send_key(vk, down)
        return True


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long), ("top", ctypes.c_long),
        ("right", ctypes.c_long), ("bottom", ctypes.c_long),
    ]


def _click_into(hwnd: int) -> None:
    rect = _RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    user32.SetCursorPos((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


# -- EDIT-target helpers (scripts/edit_target.py process) --------------------

def find_edit_target() -> tuple[int, int]:
    """(main hwnd, EDIT control hwnd) of the running edit_target process."""
    hwnd = user32.FindWindowW("ParrotypeTestTarget", None)
    if not hwnd:
        return 0, 0
    edit = user32.FindWindowExW(hwnd, None, "EDIT", None)
    return hwnd, edit


def read_edit(edit: int) -> str:
    length = user32.SendMessageW(edit, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.SendMessageW(edit, WM_GETTEXT, length + 1, buf)
    return buf.value.replace("\r\n", "\n").replace("\r", "\n")


def clear_edit(edit: int) -> None:
    """WM_SETTEXT directly to the control — no key injection involved."""
    user32.SendMessageW(edit, 0x000C, 0, "")
    time.sleep(0.1)


# -- Notepad tab cleanup ------------------------------------------------------

_DONT_SAVE_NAMES = ("don't save", "do not save", "не сохранять")


def dismiss_save_dialog(owner_pid: int, timeout_s: float = 4.0) -> bool:
    """Click "Don't save" in a Notepad save prompt owned by owner_pid.

    Strictly scoped: only touches UI belonging to the given process.
    Uses UI Automation (pywinauto) — locale-tolerant via _DONT_SAVE_NAMES.
    Returns True if a dialog was found and dismissed, False if none appeared.
    """
    from pywinauto import Application  # dev-only dependency

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            app = Application(backend="uia").connect(process=owner_pid, timeout=1)
            for window in app.windows():
                for button in window.descendants(control_type="Button"):
                    name = (button.window_text() or "").strip().lower()
                    if name in _DONT_SAVE_NAMES:
                        button.click_input()
                        time.sleep(0.4)
                        return True
        except Exception:  # noqa: BLE001 - window may vanish mid-enumeration
            pass
        time.sleep(0.3)
    return False


def close_notepad_tab(guard: FocusGuard, hwnd: int) -> bool:
    """Close OUR Notepad tab leaving no popups behind.

    Order: Ctrl+S first (a file-backed tab saves silently -> Ctrl+W is
    clean), then Ctrl+W; if a save prompt still appears (e.g. the save
    failed or the tab is untitled), click "Don't save" via UIA — never
    leave a dialog hanging on the user's screen.
    """
    pid = window_pid(hwnd)
    if not guard.acquire():
        return False
    if not guard.send_combo("ctrl+s"):
        return False
    time.sleep(0.5)
    if not guard.send_combo("ctrl+w"):
        return False
    time.sleep(0.5)
    dismiss_save_dialog(pid, timeout_s=3.0)
    return True
