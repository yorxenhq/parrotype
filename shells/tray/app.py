"""Parrotype tray application: wires hotkeys, recorder, engine, overlay, tray."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from core import Config, Engine, History, Recorder
from core.config import app_data_dir
from shells.tray import autostart, sounds
from shells.tray.hotkeys import HotkeyManager
from shells.tray.icons import TrayState, make_icon
from shells.tray.overlay import OverlayPill
from shells.tray.paste import insert_text
from shells.tray.settings import SettingsDialog

log = logging.getLogger(__name__)

MIN_RECORDING_S = 0.3


def setup_logging() -> None:
    log_path = app_data_dir() / "parrotype.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


class _Bridge(QObject):
    """Thread-safe signal bridge from audio/worker threads into the GUI."""

    level = Signal(float)
    recognized = Signal(str, float)      # text, audio_seconds — BEFORE insert attempt
    transcribed = Signal(str, float)     # text, audio_seconds — inserted OK
    insert_failed = Signal(str)          # text left on the clipboard
    failed = Signal(str)
    model_ready = Signal()


class TrayApp(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.config = Config.load()
        self.history = History(limit=self.config.history_limit)
        self.engine = Engine(self.config)
        self._engine_lock = threading.Lock()

        self.bridge = _Bridge()
        self.bridge.level.connect(self._on_level)
        self.bridge.recognized.connect(self._on_recognized)
        self.bridge.transcribed.connect(self._on_transcribed)
        self.bridge.insert_failed.connect(self._on_insert_failed)
        self.bridge.failed.connect(self._on_failed)
        self.bridge.model_ready.connect(self._update_status)

        self.recorder = Recorder(
            sample_rate=self.config.sample_rate,
            device=self.config.input_device,
            on_level=self.bridge.level.emit,
        )

        self.overlay = OverlayPill()
        self.overlay.clicked_error.connect(self._open_log)

        self.hotkeys = HotkeyManager()
        self.hotkeys.ptt_pressed.connect(self._on_ptt_pressed)
        self.hotkeys.ptt_released.connect(self._on_ptt_released)
        self.hotkeys.toggle_triggered.connect(self._on_toggle)
        self.hotkeys.cancel_pressed.connect(self._on_cancel)
        self.hotkeys.bind(self.config.hotkey_ptt, self.config.hotkey_toggle)

        self._recording = False
        self._toggle_mode = False
        self._busy = False
        self._user_paused = False        # tray-menu pause
        self._settings_open = False      # hotkeys muted while settings visible

        self.settings_dialog: SettingsDialog | None = None
        self._build_tray()
        self._preload_model()

    # -- tray -------------------------------------------------------------

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(TrayState.IDLE))
        self.tray.setToolTip("Parrotype")

        menu = QMenu()
        self.status_action = QAction("Загружаю модель…")
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        menu.addSeparator()

        self.copy_last_action = QAction("Последняя диктовка → копировать")
        self.copy_last_action.triggered.connect(self._copy_last)
        menu.addAction(self.copy_last_action)

        self.pause_action = QAction("Пауза (глушит хоткей)")
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self._on_pause_toggled)
        menu.addAction(self.pause_action)
        menu.addSeparator()

        settings_action = QAction("Настройки…")
        settings_action.triggered.connect(lambda: self._open_settings(0))
        menu.addAction(settings_action)

        history_action = QAction("История…")
        history_action.triggered.connect(lambda: self._open_settings(3))
        menu.addAction(history_action)
        menu.addSeparator()

        quit_action = QAction("Выход")
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self._menu = menu
        self._menu_actions = (
            self.status_action, self.copy_last_action, self.pause_action,
            settings_action, history_action, quit_action,
        )
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _update_status(self) -> None:
        device, compute = self.config.resolve_device()
        state = "Готов" if self.engine.model_loaded else "Модель не загружена"
        if self.hotkeys.paused:
            state = "Пауза"
        self.status_action.setText(
            f"{state} · {self.config.model_size} @ {device} ({compute})"
        )

    def _set_tray_state(self, state: TrayState) -> None:
        self.tray.setIcon(make_icon(state))

    # -- model preload -------------------------------------------------------

    def _preload_model(self) -> None:
        def worker() -> None:
            try:
                with self._engine_lock:
                    self.engine.load_model()
                self.bridge.model_ready.emit()
            except Exception as exc:
                log.exception("Model preload failed")
                self.bridge.failed.emit(f"модель не загрузилась: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    # -- recording flow --------------------------------------------------------

    def _language_label(self) -> str:
        return {"ru": "RU", "en": "EN"}.get(self.config.language, "AUTO")

    def _on_ptt_pressed(self) -> None:
        self._start_recording(toggle=False)

    def _on_ptt_released(self) -> None:
        if self._recording and not self._toggle_mode:
            self._finish_recording()

    def _on_toggle(self) -> None:
        if self._recording:
            if self._toggle_mode:
                self._finish_recording()
        else:
            self._start_recording(toggle=True)

    def _start_recording(self, toggle: bool) -> None:
        if self._recording or self._busy:
            return
        try:
            self.recorder.device = self.config.input_device
            self.recorder.start()
        except Exception as exc:
            log.exception("Recorder start failed")
            self.overlay.show_error(f"микрофон недоступен: {exc}")
            return
        self._recording = True
        self._toggle_mode = toggle
        self.hotkeys.arm_cancel()
        if self.config.sound_ticks:
            sounds.play_start()
        self.overlay.show_listening(self._language_label(), toggle)
        self._set_tray_state(TrayState.RECORDING)

    def _finish_recording(self) -> None:
        if not self._recording:
            return
        self._recording = False
        self.hotkeys.disarm_cancel()
        audio = self.recorder.stop()
        if self.config.sound_ticks:
            sounds.play_stop()
        self._set_tray_state(
            TrayState.PAUSED if self.hotkeys.paused else TrayState.IDLE
        )
        if len(audio) < MIN_RECORDING_S * self.config.sample_rate:
            self.overlay.hide_pill()
            return
        import numpy as np

        rms = float(np.sqrt(np.mean(np.square(audio))))
        peak = float(np.max(np.abs(audio)))
        log.info(
            "Captured %.1fs from device %s (rms=%.6f peak=%.6f)",
            len(audio) / self.config.sample_rate,
            self.config.input_device if self.config.input_device is not None else "default",
            rms,
            peak,
        )
        if peak < 1e-3 and rms < 1e-4:
            # Digital silence: OS/driver mute or dead device — not a "success".
            self.overlay.show_error(
                "микрофон молчит (уровень ~0) — проверь mute (F9) и устройство в настройках"
            )
            return
        self.overlay.show_transcribing()
        self._busy = True
        audio_seconds = len(audio) / self.config.sample_rate

        def worker() -> None:
            try:
                with self._engine_lock:
                    result = self.engine.transcribe(audio)
            except Exception as exc:
                log.exception("Transcription failed")
                self.bridge.failed.emit(f"ошибка распознавания: {exc}")
                return
            if not result.text:
                self.bridge.transcribed.emit("", audio_seconds)
                return
            # History is written BEFORE the insert attempt: a dictation
            # must never be lost even if insertion fails.
            self.bridge.recognized.emit(result.text, audio_seconds)
            insert = insert_text(result.text, method=self.config.insert_method)
            if insert.ok:
                self.bridge.transcribed.emit(result.text, audio_seconds)
            else:
                log.error("Insert failed (%s): %s", insert.method, insert.message)
                self.bridge.insert_failed.emit(result.text)

        threading.Thread(target=worker, daemon=True).start()

    def _on_cancel(self) -> None:
        if self._recording:
            self._recording = False
            self.hotkeys.disarm_cancel()
            self.recorder.cancel()
            self.overlay.hide_pill()
            self._set_tray_state(TrayState.IDLE)

    def _on_recognized(self, text: str, audio_seconds: float) -> None:
        # Called BEFORE the insert attempt — a dictation is never lost.
        if self.config.keep_history:
            self.history.add(text, audio_seconds)
            if self.settings_dialog and self.settings_dialog.isVisible():
                self.settings_dialog.refresh_history()

    def _on_transcribed(self, text: str, audio_seconds: float) -> None:
        self._busy = False
        if text:
            self.overlay.show_inserted(text)
        else:
            self.overlay.show_error("речь не распознана — в записи не нашлось слов")

    def _on_insert_failed(self, text: str) -> None:
        self._busy = False
        self.overlay.show_error("не смог вставить — текст в буфере, нажми Ctrl+V")

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self.overlay.show_error(message)
        self._update_status()

    def _on_level(self, rms: float) -> None:
        self.overlay.push_level(rms)

    # -- tray actions -------------------------------------------------------------

    def _copy_last(self) -> None:
        last = self.history.last
        if last:
            QApplication.clipboard().setText(last.text)

    def _on_pause_toggled(self, paused: bool) -> None:
        self._user_paused = paused
        self._apply_pause()

    def _on_settings_visibility(self, visible: bool) -> None:
        # Hotkeys are muted while the settings dialog is open so that
        # AltGr (= Ctrl+Alt on some layouts) while typing in its fields
        # does not start a recording.
        self._settings_open = visible
        self._apply_pause()

    def _apply_pause(self) -> None:
        paused = self._user_paused or self._settings_open
        self.hotkeys.set_paused(paused)
        if not self._recording:
            self._set_tray_state(TrayState.PAUSED if paused else TrayState.IDLE)
        self._update_status()

    def _open_settings(self, page: int) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self.config, self.history)
            self.settings_dialog.config_changed.connect(self._on_config_changed)
            self.settings_dialog.visibility_changed.connect(
                self._on_settings_visibility
            )
        self.settings_dialog.sidebar.setCurrentRow(page)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _on_config_changed(self) -> None:
        self.hotkeys.bind(self.config.hotkey_ptt, self.config.hotkey_toggle)
        self.engine.reload_postfilter()
        autostart.set_enabled(self.config.autostart)
        self.recorder.device = self.config.input_device
        self._update_status()

    def _open_log(self) -> None:
        log_path = app_data_dir() / "parrotype.log"
        if sys.platform == "win32" and log_path.exists():
            subprocess.Popen(["notepad.exe", str(log_path)])

    def _quit(self) -> None:
        self.hotkeys.unbind()
        if self._recording:
            self.recorder.cancel()
        self.tray.hide()
        self.app.quit()


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Parrotype")
    app.setWindowIcon(make_icon(TrayState.IDLE))

    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.error("System tray is not available")
        return 1

    tray_app = TrayApp(app)
    tray_app._update_status()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
