"""Self-test of the paste mechanism against a real Notepad window.

Verifies the exact production code path (shells.tray.paste.paste_text):
  1. sentinel on the clipboard
  2. Notepad opened and forced to the foreground (system notification
     toasts can steal focus, so activation uses a real mouse click and
     the whole attempt is retried)
  3. paste_text() -> text must appear in Notepad's RichEdit control
     (read back via WM_GETTEXT — independent of the clipboard)
  4. clipboard must be restored to the sentinel

Run: python scripts/selftest_paste.py   -> PASS/FAIL, exit 0/1
Note: interacts with the real desktop (opens/kills notepad.exe).
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shells.tray import wininput  # noqa: E402
import pyperclip  # noqa: E402

from shells.tray.paste import paste_text  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # Cyrillic in PASS/FAIL output

SENTINEL = "PARROTYPE_CLIPBOARD_SENTINEL_42"
PAYLOAD = "Parrotype paste test: проверка вставки 123, mixed RU/EN text."
ATTEMPTS = 3

user32 = ctypes.windll.user32

WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long), ("top", ctypes.c_long),
        ("right", ctypes.c_long), ("bottom", ctypes.c_long),
    ]


def find_notepad_hwnd() -> int:
    return user32.FindWindowW("Notepad", None)


def _click_into(hwnd: int) -> None:
    """Simulate a real mouse click into the window's client area (activates it)."""
    rect = _RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    x = (rect.left + rect.right) // 2
    y = (rect.top + rect.bottom) // 2
    user32.SetCursorPos(x, y)
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def force_foreground(hwnd: int) -> bool:
    """Bring hwnd to the foreground, working around the foreground lock.

    Escalation: Alt-trick + SetForegroundWindow, then a real mouse click
    (system notification toasts hold the foreground against anything else).
    """
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    for attempt in range(10):
        if user32.GetForegroundWindow() == hwnd:
            return True
        if attempt < 4:
            wininput.send_combo("alt")
            user32.SetForegroundWindow(hwnd)
        else:
            user32.BringWindowToTop(hwnd)
            _click_into(hwnd)
        time.sleep(0.2)
    return user32.GetForegroundWindow() == hwnd


def read_notepad_text(hwnd: int) -> str:
    """Read the RichEdit content of Win11 Notepad via WM_GETTEXT."""
    texts: list[str] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def collect(child, _):  # noqa: ANN001
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(child, cls, 64)
        if "RichEdit" in cls.value or cls.value == "Edit":
            length = user32.SendMessageW(child, WM_GETTEXTLENGTH, 0, 0)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.SendMessageW(child, WM_GETTEXT, length + 1, buf)
            texts.append(buf.value)
        return True

    user32.EnumChildWindows(hwnd, collect, 0)
    return "\n".join(t for t in texts if t)


def main() -> int:
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    hwnd = find_notepad_hwnd()
    if not hwnd:
        print("FAIL: Notepad window not found")
        proc.kill()
        return 1

    pasted_ok = clipboard_ok = False
    for attempt in range(1, ATTEMPTS + 1):
        pyperclip.copy(SENTINEL)
        if not force_foreground(hwnd):
            print(f"attempt {attempt}: could not foreground Notepad, retrying")
            continue

        paste_text(PAYLOAD)
        time.sleep(0.4)

        content = read_notepad_text(hwnd)
        pasted_ok = PAYLOAD in content
        clipboard_ok = pyperclip.paste() == SENTINEL
        if pasted_ok and clipboard_ok:
            break
        print(
            f"attempt {attempt}: pasted={pasted_ok} clipboard_restored={clipboard_ok} "
            f"(notepad content: {content[:60]!r})"
        )
        # clear Notepad for the next attempt
        if force_foreground(hwnd):
            wininput.send_combo("ctrl+a")
            time.sleep(0.1)
            wininput.send_combo("delete")
            time.sleep(0.2)

    print(("PASS" if pasted_ok else "FAIL") + ": text inserted into active window (Notepad)")
    print(("PASS" if clipboard_ok else "FAIL") + ": clipboard restored after paste")

    subprocess.run(
        ["taskkill", "/IM", "notepad.exe", "/F"], capture_output=True, check=False
    )
    ok = pasted_ok and clipboard_ok
    print("PASS: overall" if ok else "FAIL: overall")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
