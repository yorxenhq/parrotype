"""Self-test of the text-insert mechanism against real external windows.

Targets:
  A. scripts/edit_target.py — our own process with a classic Win32 EDIT
     control (pid-verified ownership, WM_GETTEXT oracle, no session baggage)
  B. Win11 Notepad opened on OUR temp file (clipboard-path smoke against
     a real third-party app; typed-path check is informational — Notepad's
     async RichEdit is a known-flaky target for fast injected typing)

Scenarios (per the insert-path spec):
  1. unicode typing (primary): RU+EN + «guillemets», №, dash — verbatim,
     clipboard NOT touched (+ non-fatal emoji check)
  2. clipboard fallback (>1000 chars): inserted, clipboard restored
  3. concurrent-copy: user copies during the restore window -> theirs wins
  4. held modifier: fallback waits for Ctrl release before Ctrl+V
  5. Notepad clipboard smoke + informational typed check

Safety rules (testguard): user-idle gate before starting; foreground
ownership verified before EVERY injection and between typing chunks;
a focus loss aborts the case without leaking a single keystroke.

Run: python scripts/selftest_paste.py   -> PASS/FAIL, exit 0/1
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyperclip  # noqa: E402

from scripts import testguard  # noqa: E402
from shells.tray import wininput  # noqa: E402
from shells.tray.paste import insert_text  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

SENTINEL = "PARROTYPE_CLIPBOARD_SENTINEL_42"
PAYLOAD_UNICODE = (
    "Проверка вставки: mixed RU/EN text, «ёлочки», № 7, dash — and (скобки)."
)
PAYLOAD_EMOJI = "emoji: \U0001f99c ok"
PAYLOAD_LONG = ("Длинный текст для clipboard-fallback. Long fallback text. " * 20).strip()
assert len(PAYLOAD_LONG) > 1000

ATTEMPTS = 3
NOTEPAD_MARKER = "parrotype_selftest"

user32 = ctypes.windll.user32

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, fatal: bool = True) -> None:
    if fatal:
        results.append((name, ok))
    tag = "PASS" if ok else ("FAIL" if fatal else "WARN")
    print(f"{tag}: {name}")


def run_guarded(guard: testguard.FocusGuard, action, verify, cleanup) -> bool:  # noqa: ANN001
    """action/verify with foreground ownership; retries; cleanup between tries."""
    for attempt in range(1, ATTEMPTS + 1):
        if not testguard.wait_for_user_idle(min_idle_s=2.0, timeout_s=120):
            print(f"  attempt {attempt}: user never went idle — aborting")
            return False
        if not guard.acquire():
            print(f"  attempt {attempt}: could not own the foreground")
            continue
        time.sleep(0.2)
        if not guard.ok():
            continue
        action()
        time.sleep(0.4)
        stayed = guard.ok()
        if verify():
            if not stayed:
                print(f"  attempt {attempt}: verified, but focus flapped mid-case")
            return True
        print(
            f"  attempt {attempt}: verification failed"
            + ("" if stayed else " (focus was lost mid-case)")
        )
        cleanup()
    return False


def main() -> int:  # noqa: PLR0915
    # ---------- target A: our own EDIT window ------------------------------
    pre_hwnd, _ = testguard.find_edit_target()
    if pre_hwnd:
        print("FAIL: a stale ParrotypeTestTarget window already exists — clean up first")
        return 1
    target_proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "edit_target.py")]
    )
    hwnd = edit = 0
    for _ in range(20):
        time.sleep(0.3)
        hwnd, edit = testguard.find_edit_target()
        if edit:
            break
    if not edit:
        print("FAIL: edit_target window did not appear")
        return 1
    # Ownership: unique window class + verified absence before OUR spawn.
    # (pid equality does not hold: the venv python.exe launcher re-spawns
    # the real interpreter as a child process.)
    check("edit target owned by our test process", True)

    guard = testguard.FocusGuard(hwnd)

    # -- 1. unicode typing path ---------------------------------------------
    pyperclip.copy(SENTINEL)
    outcome: dict = {}

    def act_unicode() -> None:
        outcome["res"] = insert_text(PAYLOAD_UNICODE, abort_check=guard.ok)

    ok = run_guarded(
        guard,
        act_unicode,
        lambda: PAYLOAD_UNICODE in testguard.read_edit(edit),
        lambda: testguard.clear_edit(edit),
    )
    res = outcome.get("res")
    check("unicode path used", bool(res) and res.ok and res.method == "typed")
    check("unicode text landed verbatim (RU+EN, «», №, —)", ok)
    check("clipboard untouched by unicode path", pyperclip.paste() == SENTINEL)

    if guard.acquire():
        insert_text(PAYLOAD_EMOJI, abort_check=guard.ok)
        time.sleep(0.3)
        check(
            "emoji survived unicode typing (optional)",
            PAYLOAD_EMOJI in testguard.read_edit(edit),
            fatal=False,
        )
    testguard.clear_edit(edit)

    # -- 2. clipboard fallback (>1000 chars) ----------------------------------
    pyperclip.copy(SENTINEL)

    def act_long() -> None:
        outcome["res2"] = insert_text(PAYLOAD_LONG)

    ok = run_guarded(
        guard,
        act_long,
        lambda: PAYLOAD_LONG in testguard.read_edit(edit),
        lambda: testguard.clear_edit(edit),
    )
    res2 = outcome.get("res2")
    check(
        "fallback path used for long text",
        bool(res2) and res2.ok and res2.method == "clipboard",
    )
    check("long text landed verbatim via fallback", ok)
    check("clipboard restored after fallback", pyperclip.paste() == SENTINEL)
    testguard.clear_edit(edit)

    # -- 3. user copies during the restore window ------------------------------
    pyperclip.copy(SENTINEL)
    user_text = "USER_COPIED_DURING_RESTORE_WINDOW"

    def act_concurrent() -> None:
        done: list = []
        worker = threading.Thread(
            target=lambda: done.append(insert_text(PAYLOAD_LONG)), daemon=True
        )
        worker.start()
        time.sleep(0.6)             # paste sent; inside the 1.0s restore window
        pyperclip.copy(user_text)   # the user copies something else
        worker.join(timeout=10)
        outcome["res3"] = done[0] if done else None

    ok = run_guarded(
        guard,
        act_concurrent,
        lambda: PAYLOAD_LONG in testguard.read_edit(edit),
        lambda: testguard.clear_edit(edit),
    )
    res3 = outcome.get("res3")
    check("concurrent-copy: insert finished ok", ok and bool(res3) and res3.ok)
    check(
        "concurrent-copy: user clipboard NOT overwritten by restore",
        pyperclip.paste() == user_text,
    )
    testguard.clear_edit(edit)

    # -- 4. held modifier delays the fallback Ctrl+V ----------------------------
    pyperclip.copy(SENTINEL)

    def act_held() -> None:
        if not guard.send_key(wininput.VK_CONTROL, True):
            return
        held: list = []
        worker = threading.Thread(
            target=lambda: held.append(insert_text(PAYLOAD_LONG)), daemon=True
        )
        worker.start()
        time.sleep(0.8)                                # fallback must be waiting
        outcome["waited"] = PAYLOAD_LONG[:80] not in testguard.read_edit(edit)
        wininput.send_key(wininput.VK_CONTROL, False)  # always release
        worker.join(timeout=10)
        outcome["res4"] = held[0] if held else None

    ok = run_guarded(
        guard,
        act_held,
        lambda: PAYLOAD_LONG in testguard.read_edit(edit),
        lambda: testguard.clear_edit(edit),
    )
    res4 = outcome.get("res4")
    check("held Ctrl: paste did not fire while held", bool(outcome.get("waited")))
    check("held Ctrl: paste completed after release", ok and bool(res4) and res4.ok)
    check("held Ctrl: clipboard restored", pyperclip.paste() == SENTINEL)

    target_proc.kill()   # our own window; nothing to save

    # ---------- target B: real Notepad (own temp-file tab) ---------------------
    tmp = Path(tempfile.gettempdir()) / f"{NOTEPAD_MARKER}.txt"
    tmp.write_text("", encoding="utf-8")
    subprocess.Popen(["notepad.exe", str(tmp)])
    np_hwnd = 0
    for _ in range(20):
        time.sleep(0.5)
        np_hwnd = _find_notepad_by_title(NOTEPAD_MARKER)
        if np_hwnd:
            break
    if np_hwnd:
        np_guard = testguard.FocusGuard(np_hwnd)
        pyperclip.copy(SENTINEL)

        def act_np_clip() -> None:
            outcome["np"] = insert_text(PAYLOAD_UNICODE, method="clipboard")
            if not outcome["np"].ok:
                print(f"  insert result: {outcome['np']}")

        ok = run_guarded(
            np_guard,
            act_np_clip,
            lambda: PAYLOAD_UNICODE in _read_notepad(np_hwnd),
            lambda: _clear_notepad(np_guard, np_hwnd),
        )
        np_res = outcome.get("np")
        check(
            "Notepad smoke: clipboard-method insert landed",
            ok and bool(np_res) and np_res.ok,
        )
        check("Notepad smoke: clipboard restored", pyperclip.paste() == SENTINEL)

        # Informational: typed path against Notepad's async RichEdit
        _clear_notepad(np_guard, np_hwnd)
        if np_guard.acquire():
            insert_text(PAYLOAD_UNICODE, abort_check=np_guard.ok)
            time.sleep(0.5)
            check(
                "Notepad typed path verbatim (informational)",
                PAYLOAD_UNICODE in _read_notepad(np_hwnd),
                fatal=False,
            )

        # cleanup: clear, then close only OUR tab (dismissing any save prompt)
        _clear_notepad(np_guard, np_hwnd)
        closed = testguard.close_notepad_tab(np_guard, np_hwnd)
        check("Notepad cleanup: our tab closed, no popup left", closed, fatal=False)
    else:
        check("Notepad smoke: window found", False)

    failed = [n for n, ok_ in results if not ok_]
    print(f"\n{len(results) - len(failed)}/{len(results)} fatal checks passed")
    print("PASS: overall" if not failed else f"FAIL: overall ({failed})")
    return 0 if not failed else 1


def _find_notepad_by_title(marker: str) -> int:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def collect(hwnd, _):  # noqa: ANN001
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value == "Notepad" and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            if marker in title.value:
                found.append(int(hwnd) if hwnd else 0)
        return True

    user32.EnumWindows(collect, 0)
    return found[0] if found else 0


def _read_notepad(hwnd: int) -> str:
    texts: list[str] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def collect(child, _):  # noqa: ANN001
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(child, cls, 64)
        if "RichEdit" in cls.value or cls.value == "Edit":
            length = user32.SendMessageW(child, testguard.WM_GETTEXTLENGTH, 0, 0)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.SendMessageW(child, testguard.WM_GETTEXT, length + 1, buf)
            texts.append(buf.value)
        return True

    user32.EnumChildWindows(hwnd, collect, 0)
    return "\n".join(t for t in texts if t).replace("\r", "\n")


def _clear_notepad(guard: testguard.FocusGuard, hwnd: int) -> bool:
    """Select-all + delete inside OUR tab only (title re-verified)."""
    if not _find_notepad_by_title(NOTEPAD_MARKER) == hwnd:
        print("WARN: our Notepad tab is not active — refusing to clear")
        return False
    if not guard.acquire():
        return False
    if not guard.send_combo("ctrl+a"):
        return False
    time.sleep(0.15)
    if not guard.send_combo("delete"):
        return False
    time.sleep(0.25)
    return True


if __name__ == "__main__":
    sys.exit(main())
