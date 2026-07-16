"""Headless self-test of the tray app: start, drive overlay states, quit.

Verifies (without microphone or hotkeys):
  - QApplication + TrayApp construct without crashing
  - tray icon is created and visible
  - overlay pill shows/hides programmatically through all states
  - overlay window does not accept focus (flag check)

Run: python scripts/selftest_tray.py   -> prints PASS/FAIL lines, exit code 0/1
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" ({detail})" if detail else ""))


def main() -> int:
    from shells.tray.app import TrayApp, setup_logging

    setup_logging()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    check("system tray available", QSystemTrayIcon.isSystemTrayAvailable())

    tray_app = TrayApp(app)
    check("TrayApp constructed", True)
    check("tray icon visible", tray_app.tray.isVisible())
    check(
        "tray menu has expected actions",
        len(tray_app._menu.actions()) >= 6,
        f"{len(tray_app._menu.actions())} actions",
    )

    overlay = tray_app.overlay

    def step_listening() -> None:
        overlay.show_listening("AUTO", toggle_mode=False)
        for level in (0.05, 0.2, 0.4, 0.1):
            overlay.push_level(level)
        check("overlay LISTENING visible", overlay.isVisible())
        check(
            "overlay does not accept focus",
            bool(overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus),
        )
        check(
            "overlay click-through in LISTENING",
            bool(overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput),
        )

    def step_transcribing() -> None:
        overlay.show_transcribing()
        check("overlay TRANSCRIBING visible", overlay.isVisible())

    def step_inserted() -> None:
        overlay.show_inserted("Привет, собери отчёт по проекту")
        check("overlay INSERTED visible", overlay.isVisible())
        check("preview text set", "Привет" in overlay.preview_text)

    def step_error() -> None:
        overlay.show_error("микрофон занят другим приложением")
        check("overlay ERROR visible", overlay.isVisible())
        check(
            "overlay clickable in ERROR",
            not bool(overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput),
        )

    def step_hide() -> None:
        overlay.hide_pill()
        check("overlay hidden", not overlay.isVisible())

    def step_settings_mute() -> None:
        check("hotkeys active before settings", not tray_app.hotkeys.paused)
        tray_app._open_settings(0)
        check("hotkeys muted while settings open", tray_app.hotkeys.paused)
        tray_app.settings_dialog.hide()
        check("hotkeys restored after settings closed", not tray_app.hotkeys.paused)
        # user pause must survive a settings open/close cycle
        tray_app.pause_action.setChecked(True)
        tray_app._open_settings(0)
        tray_app.settings_dialog.hide()
        check("user pause survives settings cycle", tray_app.hotkeys.paused)
        tray_app.pause_action.setChecked(False)
        check("user unpause works", not tray_app.hotkeys.paused)

    def finish() -> None:
        tray_app._quit()

    QTimer.singleShot(300, step_listening)
    QTimer.singleShot(1200, step_transcribing)
    QTimer.singleShot(1800, step_inserted)
    QTimer.singleShot(3200, step_error)
    QTimer.singleShot(3800, step_hide)
    QTimer.singleShot(4200, step_settings_mute)
    QTimer.singleShot(5200, finish)

    app.exec()

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
