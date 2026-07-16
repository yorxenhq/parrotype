"""Parrotype tray application: wires hotkeys, recorder, engine, overlay, tray."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from core import Config, Engine, History, Recorder
from core.audio import pick_input_device, probe_peak
from core.config import app_data_dir
from shells.tray import autostart, micguard, singleinstance, sounds, theme
from shells.tray.hotkeys import HotkeyManager
from shells.tray.i18n import current_language, set_language, tr
from shells.tray.icons import TrayState, make_icon
from shells.tray.overlay import OverlayPill
from shells.tray.paste import insert_text
from shells.tray.settings import SettingsDialog
from shells.tray.wizard import FirstRunWizard

log = logging.getLogger(__name__)

MIN_RECORDING_S = 0.3


def setup_logging() -> None:
    log_path = app_data_dir() / "parrotype.log"
    handlers: list[logging.Handler] = [
        logging.FileHandler(log_path, encoding="utf-8")
    ]
    # A windowed build may have no usable stderr; the file handler must
    # never be lost because the stream handler cannot be constructed.
    if sys.stderr is not None:
        try:
            handlers.append(logging.StreamHandler())
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


class _Bridge(QObject):
    """Thread-safe signal bridge from audio/worker threads into the GUI."""

    level = Signal(float)
    recognized = Signal(str, float)      # text, audio_seconds — BEFORE insert attempt
    transcribed = Signal(str, float)     # text, audio_seconds — inserted OK
    insert_failed = Signal(str)          # text left on the clipboard
    failed = Signal(str)
    model_progress = Signal(int)         # download percent
    model_ready = Signal()
    self_check = Signal(str, str)        # title, body -> tray balloon


class TrayApp(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.config = Config.load()
        set_language(self.config.ui_language)
        self.history = History(limit=self.config.history_limit)
        self.engine = Engine(self.config)
        self._engine_lock = threading.Lock()

        self.bridge = _Bridge()
        self.bridge.level.connect(self._on_level)
        self.bridge.recognized.connect(self._on_recognized)
        self.bridge.transcribed.connect(self._on_transcribed)
        self.bridge.insert_failed.connect(self._on_insert_failed)
        self.bridge.failed.connect(self._on_failed)
        self.bridge.model_progress.connect(self._on_model_progress)
        self.bridge.model_ready.connect(self._on_model_ready)
        self.bridge.self_check.connect(self._on_self_check_warning)

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
        self._wizard_active = False

        self.settings_dialog: SettingsDialog | None = None
        self._settings_language = current_language()
        self.wizard: FirstRunWizard | None = None
        self._build_tray()
        if self.config.first_run_done:
            # First run defers the preload: the wizard picks the model first.
            self._preload_model()

    # -- tray -------------------------------------------------------------

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(TrayState.IDLE))
        self.tray.setToolTip("Parrotype")

        menu = QMenu()
        self.status_action = QAction(tr("tray.loading_model"))
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        menu.addSeparator()

        self.copy_last_action = QAction(tr("tray.copy_last"))
        self.copy_last_action.triggered.connect(self._copy_last)
        menu.addAction(self.copy_last_action)

        self.pause_action = QAction(tr("tray.pause"))
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self._on_pause_toggled)
        menu.addAction(self.pause_action)
        menu.addSeparator()

        self.settings_action = QAction(tr("tray.settings"))
        self.settings_action.triggered.connect(lambda: self._open_settings(0))
        menu.addAction(self.settings_action)

        self.history_action = QAction(tr("tray.history"))
        self.history_action.triggered.connect(lambda: self._open_settings(3))
        menu.addAction(self.history_action)
        menu.addSeparator()

        self.quit_action = QAction(tr("tray.quit"))
        self.quit_action.triggered.connect(self._quit)
        menu.addAction(self.quit_action)

        self._menu = menu
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _retranslate_tray(self) -> None:
        self.copy_last_action.setText(tr("tray.copy_last"))
        self.pause_action.setText(tr("tray.pause"))
        self.settings_action.setText(tr("tray.settings"))
        self.history_action.setText(tr("tray.history"))
        self.quit_action.setText(tr("tray.quit"))
        self._update_status()

    def _update_status(self) -> None:
        device, compute = self.config.resolve_device()
        state = tr("tray.ready") if self.engine.model_loaded else tr("tray.model_not_loaded")
        if self.hotkeys.paused:
            state = tr("tray.paused")
        self.status_action.setText(
            f"{state} · {self.config.model_size} @ {device} ({compute})"
        )

    def _set_tray_state(self, state: TrayState) -> None:
        self.tray.setIcon(make_icon(state))

    # -- first-run wizard -------------------------------------------------

    def maybe_show_wizard(self) -> bool:
        """Show the first-run wizard when needed. Returns True if shown."""
        if self.config.first_run_done:
            return False
        self._wizard_active = True
        self.wizard = FirstRunWizard(self.config)
        self.wizard.finished_ok.connect(self._on_wizard_done)
        self.wizard.rejected.connect(self._on_wizard_done)
        # As soon as the wizard has the model on disk (step 2), load and
        # warm it in the background so step 3 "try dictating" is instant.
        self.wizard.model_available.connect(self._preload_model)
        self.wizard.show()
        self.wizard.raise_()
        self.wizard.activateWindow()
        return True

    def _on_wizard_done(self) -> None:
        self._wizard_active = False
        self.wizard = None
        self._on_config_changed()
        self._preload_model()
        QTimer.singleShot(1500, self._startup_self_check)

    # -- model preload -------------------------------------------------------

    def _preload_model(self) -> None:
        def worker() -> None:
            try:
                last_pct = {"v": -5}

                def on_pct(pct: int) -> None:
                    if pct >= last_pct["v"] + 2 or pct == 100:
                        last_pct["v"] = pct
                        self.bridge.model_progress.emit(pct)

                with self._engine_lock:
                    if not self.engine.is_model_cached():
                        self.engine.ensure_model(progress_cb=on_pct)
                    self.engine.load_model()
                    # Throwaway decode: without it the first real dictation
                    # pays the CUDA cold-start and feels sluggish.
                    self.engine.warm_up()
                self.bridge.model_ready.emit()
                self._maybe_selftest()
            except Exception as exc:
                log.exception("Model preload failed")
                self.bridge.failed.emit(tr("pill.model_failed", err=exc))

        threading.Thread(target=worker, daemon=True).start()

    def _maybe_selftest(self) -> None:
        """Headless release check: PARROTYPE_SELFTEST_WAV=<path> makes the app
        transcribe that file right after model warm-up, log the result and
        exit. Exercises the exact code path that crashed the windowed build
        (native decode with no console attached)."""
        wav = os.environ.get("PARROTYPE_SELFTEST_WAV")
        if not wav:
            return
        try:
            import wave

            import numpy as np

            with wave.open(wav, "rb") as f:
                frames = f.readframes(f.getnframes())
                rate = f.getframerate()
            audio = (
                np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            )
            if rate != self.config.sample_rate:
                idx = np.linspace(
                    0, len(audio) - 1, int(len(audio) * self.config.sample_rate / rate)
                ).astype(np.int64)
                audio = audio[idx]
            with self._engine_lock:
                result = self.engine.transcribe(audio)
            log.info("SELFTEST OK: %r", result.text[:120])
            code = 0
        except Exception:
            log.exception("SELFTEST FAILED")
            code = 3
        QTimer.singleShot(0, lambda: self.app.exit(code))

    def _on_model_progress(self, pct: int) -> None:
        text = tr("pill.downloading_model", pct=pct)
        self.status_action.setText(text)
        if not self._recording and not self._busy and not self._wizard_active:
            self.overlay.show_status(text)

    def _on_model_ready(self) -> None:
        from shells.tray.overlay import OverlayState

        if self.overlay.state == OverlayState.STATUS:
            self.overlay.hide_pill()
        self._update_status()

    # -- startup self-check -----------------------------------------------------

    def _startup_self_check(self) -> None:
        """0.5s capture probe + endpoint-mute check, off the GUI thread."""
        if self._wizard_active:
            return

        def worker() -> None:
            try:
                if micguard.default_mic_muted():
                    self.bridge.self_check.emit(
                        tr("tray.mic_silent_title"), tr("pill.mic_muted")
                    )
                    return
                if self._recording or self._busy:
                    return
                device = pick_input_device(self.config.input_device)
                peak = probe_peak(device, seconds=0.5, sample_rate=self.config.sample_rate)
                log.info("Startup self-check: device=%s peak=%.6f", device, peak)
                if peak < 1e-6:
                    self.bridge.self_check.emit(
                        tr("tray.mic_silent_title"), tr("tray.mic_silent_body")
                    )
            except Exception:
                log.exception("Startup self-check failed")

        threading.Thread(target=worker, daemon=True).start()

    def _on_self_check_warning(self, title: str, body: str) -> None:
        self.tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Warning, 8000)

    # -- recording flow --------------------------------------------------------

    def _language_label(self) -> str:
        lang = self.config.language
        return "AUTO" if lang == "auto" else lang.upper()

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
        if micguard.default_mic_muted():
            # One-click unmute, but only on the user's explicit click.
            self.overlay.show_error(tr("pill.mic_muted"), action=self._unmute_mic)
            return
        try:
            self.recorder.device = pick_input_device(self.config.input_device)
            self.recorder.start()
        except Exception as exc:
            log.exception("Recorder start failed")
            self.overlay.show_error(tr("pill.mic_unavailable", err=exc))
            return
        self._recording = True
        self._toggle_mode = toggle
        self.hotkeys.arm_cancel()
        if self.config.sound_ticks:
            sounds.play_start()
        self.overlay.show_listening(self._language_label(), toggle)
        self._set_tray_state(TrayState.RECORDING)

    def _unmute_mic(self) -> None:
        if micguard.unmute_default_mic():
            self.overlay.show_inserted(tr("pill.mic_unmuted"))
        else:
            self.overlay.show_error(tr("pill.mic_silent"))

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
            self.recorder.device if self.recorder.device is not None else "default",
            rms,
            peak,
        )
        if peak < 1e-3 and rms < 1e-4:
            # Digital silence: OS/driver mute or dead device — not a "success".
            self.overlay.show_error(tr("pill.mic_silent"))
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
                self.bridge.failed.emit(tr("pill.transcribe_error", err=exc))
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
            self.overlay.show_error(tr("pill.no_speech"))

    def _on_insert_failed(self, text: str) -> None:
        self._busy = False
        self.overlay.show_error(tr("pill.insert_failed"))

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
        if self.settings_dialog is not None and self._settings_language != current_language():
            self.settings_dialog.deleteLater()
            self.settings_dialog = None
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self.config, self.history)
            self._settings_language = current_language()
            self.settings_dialog.config_changed.connect(self._on_config_changed)
            self.settings_dialog.visibility_changed.connect(
                self._on_settings_visibility
            )
        self.settings_dialog.sidebar.setCurrentRow(page)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _on_config_changed(self) -> None:
        previous_language = current_language()
        set_language(self.config.ui_language)
        if current_language() != previous_language:
            self._retranslate_tray()
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
    if not singleinstance.acquire():
        # Second copy would fight the first over the global hotkey hook.
        set_language(Config.load().ui_language)
        log.info("Another Parrotype instance is already running; exiting")
        singleinstance.notify_already_running(
            tr("app.already_running_title"), tr("app.already_running")
        )
        return 0
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Parrotype")
    app.setWindowIcon(make_icon(TrayState.IDLE))

    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.error("System tray is not available")
        return 1

    theme.load_fonts()
    tray_app = TrayApp(app)
    app.setStyleSheet(theme.app_qss())
    tray_app._update_status()
    if not tray_app.maybe_show_wizard():
        QTimer.singleShot(2500, tray_app._startup_self_check)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
