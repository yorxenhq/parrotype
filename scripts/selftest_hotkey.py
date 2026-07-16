"""Self-test of global hotkey plumbing without a human at the keyboard.

Injects key events via SendInput (shells.tray.wininput); injected input
passes through the real WH_KEYBOARD_LL hook, so this verifies OS-level
hook installation, PTT press/release detection, toggle detection,
Esc-cancel arming and the pause gate.

It does NOT prove hotkeys win over every foreground app (browser /
VS Code / Telegram) — that needs a human check.

Run: python scripts/selftest_hotkey.py   -> PASS/FAIL, exit 0/1
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from shells.tray.hotkeys import HotkeyManager, validate_combo  # noqa: E402
from shells.tray import wininput  # noqa: E402

events: list[str] = []
results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}: {name}")


def _press(*names: str) -> None:
    for n in names:
        wininput.send_key(wininput._NAME_TO_VK[n], True)


def _release(*names: str) -> None:
    for n in names:
        wininput.send_key(wininput._NAME_TO_VK[n], False)


def main() -> int:
    app = QCoreApplication(sys.argv)

    check(
        "combo validation accepts good combos",
        validate_combo("ctrl+alt") and validate_combo("f9"),
    )
    check("combo validation rejects garbage", not validate_combo("not+a+key+at+all"))

    manager = HotkeyManager()
    manager.ptt_pressed.connect(lambda: events.append("ptt_down"))
    manager.ptt_released.connect(lambda: events.append("ptt_up"))
    manager.toggle_triggered.connect(lambda: events.append("toggle"))
    manager.cancel_pressed.connect(lambda: events.append("cancel"))
    manager.bind("ctrl+alt", "ctrl+shift+space")

    def scenario() -> None:
        time.sleep(0.3)  # let the hook thread install

        # PTT: hold ctrl+alt, release
        _press("ctrl", "alt")
        time.sleep(0.2)
        _release("alt", "ctrl")
        time.sleep(0.2)

        # Toggle: ctrl+shift+space
        _press("ctrl", "shift", "space")
        time.sleep(0.15)
        _release("space", "shift", "ctrl")
        time.sleep(0.2)

        # Esc-cancel: armed -> fires; disarmed -> silent
        manager.arm_cancel()
        _press("esc"); _release("esc")
        time.sleep(0.2)
        manager.disarm_cancel()
        _press("esc"); _release("esc")
        time.sleep(0.2)

        # Pause gate: no events while paused
        before = len(events)
        manager.set_paused(True)
        _press("ctrl", "alt")
        time.sleep(0.15)
        _release("alt", "ctrl")
        time.sleep(0.2)
        manager.set_paused(False)
        paused_silent = len(events) == before

        app.processEvents()
        check("PTT press detected", "ptt_down" in events)
        check("PTT release detected", "ptt_up" in events)
        check("toggle detected", "toggle" in events)
        check("toggle did not trigger PTT", events.count("ptt_down") == 1)
        check("Esc cancel fires when armed, once", events.count("cancel") == 1)
        check("pause gate silences hotkeys", paused_silent)

        manager.unbind()
        app.quit()

    QTimer.singleShot(200, scenario)
    app.exec()

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    print("events:", events)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
