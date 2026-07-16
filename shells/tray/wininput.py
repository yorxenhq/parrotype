"""Windows keyboard input, self-contained on ctypes.

Provides:
  - KeyboardHook: WH_KEYBOARD_LL global hook (press/release with VK codes)
  - parse_combo / combo names -> VK sets
  - send_paste / send_key: SendInput-based key injection

Written in-repo because the unmaintained `keyboard` package silently
receives no hook events on Python 3.13 (verified: a raw ctypes LL hook
in the same process works fine).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
WM_QUIT = 0x0012

VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN = 0x10, 0x11, 0x12, 0x5B

# Left/right variants -> generic
_GENERIC_VK = {
    0xA0: VK_SHIFT, 0xA1: VK_SHIFT,
    0xA2: VK_CONTROL, 0xA3: VK_CONTROL,
    0xA4: VK_MENU, 0xA5: VK_MENU,
    0x5C: VK_LWIN,
}

_NAME_TO_VK: dict[str, int] = {
    "ctrl": VK_CONTROL, "control": VK_CONTROL,
    "alt": VK_MENU, "menu": VK_MENU,
    "shift": VK_SHIFT,
    "win": VK_LWIN, "windows": VK_LWIN,
    "space": 0x20, "esc": 0x1B, "escape": 0x1B,
    "tab": 0x09, "enter": 0x0D, "return": 0x0D, "backspace": 0x08,
    "capslock": 0x14, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "\\": 0xDC,
}
for _i in range(1, 25):
    _NAME_TO_VK[f"f{_i}"] = 0x70 + _i - 1
for _c in "abcdefghijklmnopqrstuvwxyz":
    _NAME_TO_VK[_c] = ord(_c.upper())
for _d in "0123456789":
    _NAME_TO_VK[_d] = ord(_d)


def parse_combo(combo: str) -> frozenset[int]:
    """'ctrl+alt+space' -> frozenset of VK codes. Raises ValueError."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("empty combo")
    vks = set()
    for part in parts:
        if part not in _NAME_TO_VK:
            raise ValueError(f"unknown key name: {part!r}")
        vks.add(_NAME_TO_VK[part])
    return frozenset(vks)


def validate_combo(combo: str) -> bool:
    try:
        parse_combo(combo)
        return True
    except ValueError:
        return False


# -- low-level hook ---------------------------------------------------------

_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wt.WPARAM, wt.LPARAM)

user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, _HOOKPROC, wt.HINSTANCE, wt.DWORD)
user32.CallNextHookEx.restype = ctypes.c_longlong
user32.CallNextHookEx.argtypes = (ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wt.DWORD),
        ("scanCode", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KeyboardHook:
    """Global keyboard hook. Calls on_event(vk, is_down) from the hook thread.

    The callback must be fast (Windows drops slow LL hooks); do not do
    heavy work inside it — emit a queued signal instead.
    """

    def __init__(self, on_event: Callable[[int, bool], None]):
        self._on_event = on_event
        self._hook_id: int | None = None
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._proc = _HOOKPROC(self._callback)   # keep a reference alive

    def _callback(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code >= 0:
            kbd = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            vk = _GENERIC_VK.get(kbd.vkCode, kbd.vkCode)
            if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                self._safe_emit(vk, True)
            elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                self._safe_emit(vk, False)
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _safe_emit(self, vk: int, down: bool) -> None:
        try:
            self._on_event(vk, down)
        except Exception:  # never propagate into the OS hook chain
            log.exception("Keyboard hook handler failed")

    def _pump(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook_id = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook_id:
            log.error("SetWindowsHookExW failed: %s", kernel32.GetLastError())
            return
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(self._hook_id)
        self._hook_id = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._pump, daemon=True, name="parrotype-kbd-hook"
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread = None
        self._thread_id = None

    @property
    def active(self) -> bool:
        return self._hook_id is not None


# -- key injection (SendInput) ------------------------------------------------

_KEYEVENTF_KEYUP = 0x0002
_INPUT_KEYBOARD = 1
ULONG_PTR = ctypes.c_size_t


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
        ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("padding", ctypes.c_byte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("union", _INPUTUNION)]


def send_key(vk: int, down: bool) -> None:
    inp = _INPUT()
    inp.type = _INPUT_KEYBOARD
    inp.union.ki = _KEYBDINPUT(vk, 0, 0 if down else _KEYEVENTF_KEYUP, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def send_combo(combo: str) -> None:
    """Press and release a combo, modifiers first (e.g. 'ctrl+v')."""
    vks = []
    for part in [p.strip().lower() for p in combo.split("+") if p.strip()]:
        vks.append(_NAME_TO_VK[part])
    for vk in vks:
        send_key(vk, True)
    for vk in reversed(vks):
        send_key(vk, False)


def send_paste() -> None:
    send_combo("ctrl+v")
