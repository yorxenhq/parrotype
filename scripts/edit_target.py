"""Minimal Win32 window with a classic EDIT control — external paste target.

Used by selftest_paste.py as a clean, controlled target process for insert
tests (Win11 Notepad's async RichEdit corrupts fast injected typing, so it
cannot serve as a typed-path oracle; a classic EDIT control handles both
typed and clipboard input correctly).

Run: python scripts/edit_target.py   (window class: ParrotypeTestTarget)
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)

kernel32.GetModuleHandleW.restype = ctypes.c_void_p
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.DefWindowProcW.argtypes = (wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)
user32.CreateWindowExW.restype = ctypes.c_void_p
user32.CreateWindowExW.argtypes = (
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
)


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p), ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p), ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
    ]


@WNDPROC
def _wndproc(hwnd, msg, wparam, lparam):  # noqa: ANN001
    if msg == 0x0002:  # WM_DESTROY
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def main() -> None:
    wc = WNDCLASS()
    wc.lpfnWndProc = _wndproc
    wc.lpszClassName = "ParrotypeTestTarget"
    wc.hInstance = kernel32.GetModuleHandleW(None)
    user32.RegisterClassW(ctypes.byref(wc))

    hwnd = user32.CreateWindowExW(
        0, "ParrotypeTestTarget", "parrotype_edit_target",
        0x10CF0000,  # WS_OVERLAPPEDWINDOW | WS_VISIBLE
        100, 100, 600, 200, None, None, wc.hInstance, None,
    )
    edit = user32.CreateWindowExW(
        0, "EDIT", "",
        0x50810044,  # WS_CHILD | WS_VISIBLE | WS_BORDER | ES_MULTILINE | ES_AUTOVSCROLL
        5, 5, 570, 150, hwnd, None, wc.hInstance, None,
    )
    user32.ShowWindow(hwnd, 5)
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(edit)

    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    main()
