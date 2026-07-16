"""Settings window: single dialog ~760x500 with left sidebar.

Pages: General / Model / Dictionary / History / About.
Quiet-tool style: no dashboards, no stats, no branding inside the UI.
Includes a live microphone level meter (runs only while the dialog is
visible — dictation hotkeys are muted then, so the device is free).
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import APP_VERSION, Config, Engine, History, Recorder, list_input_devices
from shells.tray import theme, updates
from shells.tray.hotkeys import validate_combo
from shells.tray.i18n import tr
from shells.tray.modelpicker import SIZES, ModelOption, ModelPicker, machine_options
from shells.tray.native import enable_dark_titlebar

log = logging.getLogger(__name__)

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]

_TEST_WAV = Path(__file__).resolve().parents[2] / "assets" / "latency_test.wav"


class LevelMeter(QWidget):
    """Thin live input-level bar (accent fill, muted track)."""

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setFixedHeight(8)
        self.setMinimumWidth(180)
        self._level = 0.0            # smoothed 0..1

    def push(self, rms: float) -> None:
        target = min(1.0, rms * 6.0)
        self._level = max(target, self._level * 0.85)
        self.update()

    def reset(self) -> None:
        self._level = 0.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.LINE))
        painter.drawRoundedRect(self.rect(), 4, 4)
        width = int(self.width() * self._level)
        if width > 2:
            painter.setBrush(QColor(theme.ACCENT))
            painter.drawRoundedRect(0, 0, width, self.height(), 4, 4)
        painter.end()


class SettingsDialog(QDialog):
    config_changed = Signal()
    visibility_changed = Signal(bool)   # True while the dialog is on screen
    _latency_done = Signal(str)
    _level = Signal(float)

    def __init__(self, config: Config, history: History, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.config = config
        self.history = history
        self.setWindowTitle(tr("set.title"))
        self.resize(760, 560)

        self._monitor: Recorder | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(160)
        self.sidebar.setObjectName("sidebar")
        for key in ("general", "model", "dictionary", "history", "about"):
            QListWidgetItem(tr(f"set.nav.{key}"), self.sidebar)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_general_page())
        self.pages.addWidget(self._build_model_page())
        self.pages.addWidget(self._build_dictionary_page())
        self.pages.addWidget(self._build_history_page())
        self.pages.addWidget(self._build_about_page())

        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

        root.addWidget(self.sidebar)
        root.addWidget(self.pages, 1)

        self._latency_done.connect(self._show_latency_result)
        self._level.connect(self._on_level)
        self._apply_style()

    def showEvent(self, event) -> None:  # noqa: N802, ANN001
        super().showEvent(event)
        enable_dark_titlebar(self)
        self.visibility_changed.emit(True)
        QTimer.singleShot(150, self._start_monitor)

    def hideEvent(self, event) -> None:  # noqa: N802, ANN001
        super().hideEvent(event)
        self._stop_monitor()
        self.visibility_changed.emit(False)

    # -- live level monitor ------------------------------------------------

    def _start_monitor(self) -> None:
        if self._monitor is not None or not self.isVisible():
            return
        try:
            self._monitor = Recorder(
                sample_rate=self.config.sample_rate,
                device=self.config.input_device,
                on_level=self._level.emit,
            )
            self._monitor.start()
        except Exception as exc:
            log.warning("Level monitor unavailable: %s", exc)
            self._monitor = None

    def _stop_monitor(self) -> None:
        if self._monitor is not None:
            try:
                self._monitor.cancel()
            finally:
                self._monitor = None
            self.level_meter.reset()

    def _restart_monitor(self) -> None:
        self._stop_monitor()
        self._start_monitor()

    def _on_level(self, rms: float) -> None:
        self.level_meter.push(rms)

    # -- pages -------------------------------------------------------------

    def _build_general_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)

        self.ptt_edit = QLineEdit(self.config.hotkey_ptt)
        self.ptt_edit.setPlaceholderText(tr("set.hotkey_ptt_ph"))
        self.ptt_edit.editingFinished.connect(self._save_hotkeys)
        form.addRow(tr("set.hotkey_ptt"), self.ptt_edit)

        self.toggle_edit = QLineEdit(self.config.hotkey_toggle)
        self.toggle_edit.setPlaceholderText(tr("set.hotkey_toggle_ph"))
        self.toggle_edit.editingFinished.connect(self._save_hotkeys)
        form.addRow(tr("set.hotkey_toggle"), self.toggle_edit)

        # Recognition languages: auto-detect + the set that passed the
        # measured quality gate (scripts/lang_gate.py, >=80% keyword recall
        # on large-v3-turbo) — see design/preview/lang-gate.md.
        self.lang_combo = QComboBox()
        for label, code in (
            ("Auto", "auto"), ("Русский", "ru"), ("English", "en"),
            ("Español", "es"), ("Deutsch", "de"), ("Français", "fr"),
            ("Italiano", "it"), ("Português", "pt"), ("Polski", "pl"),
            ("Українська", "uk"), ("Nederlands", "nl"), ("Türkçe", "tr"),
            ("日本語", "ja"), ("한국어", "ko"), ("中文", "zh"),
        ):
            self.lang_combo.addItem(label, code)
        _select_by_data(self.lang_combo, self.config.language)
        self.lang_combo.currentIndexChanged.connect(self._save_general)
        form.addRow(tr("set.language"), self.lang_combo)

        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.addItem(tr("set.ui_lang.auto"), "auto")
        self.ui_lang_combo.addItem("Русский", "ru")
        self.ui_lang_combo.addItem("English", "en")
        _select_by_data(self.ui_lang_combo, self.config.ui_language)
        self.ui_lang_combo.currentIndexChanged.connect(self._save_general)
        form.addRow(tr("set.ui_language"), self.ui_lang_combo)

        self.insert_combo = QComboBox()
        self.insert_combo.addItem(tr("set.insert.type"), "auto")
        self.insert_combo.addItem(tr("set.insert.clipboard"), "clipboard")
        _select_by_data(self.insert_combo, self.config.insert_method)
        self.insert_combo.currentIndexChanged.connect(self._save_general)
        self.insert_combo.setToolTip(tr("set.insert_tip"))
        form.addRow(tr("set.insert_method"), self.insert_combo)

        self.mic_combo = QComboBox()
        self.mic_combo.addItem(tr("set.mic_default"), None)
        try:
            for idx, name in list_input_devices(skip_virtual=True):
                self.mic_combo.addItem(name, idx)
        except Exception as exc:
            log.error("Cannot list input devices: %s", exc)
        if self.config.input_device is not None:
            _select_by_data(self.mic_combo, self.config.input_device)
        self.mic_combo.currentIndexChanged.connect(self._save_general)
        form.addRow(tr("set.microphone"), self.mic_combo)

        self.level_meter = LevelMeter()
        form.addRow(tr("set.mic_level"), self.level_meter)

        self.autostart_check = QCheckBox(tr("set.autostart_cb"))
        self.autostart_check.setChecked(self.config.autostart)
        self.autostart_check.toggled.connect(self._save_general)
        form.addRow(tr("set.autostart"), self.autostart_check)

        self.sound_check = QCheckBox(tr("set.sound_cb"))
        self.sound_check.setChecked(self.config.sound_ticks)
        self.sound_check.toggled.connect(self._save_general)
        form.addRow(tr("set.sound"), self.sound_check)

        return page

    def _build_model_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        options, note = machine_options()
        if self.config.model_size not in {o.name for o in options}:
            # Hand-picked model outside the recommended trio (e.g. large-v3):
            # show it as a fourth card so the selection stays honest.
            size_n, size_unit = SIZES.get(self.config.model_size, ("—", "gb"))
            options = [
                *options,
                ModelOption(self.config.model_size, "model.desc.other",
                            "—", size_n, size_unit),
            ]
        self.model_picker = ModelPicker(options, self.config.model_size, note)
        self.model_picker.changed.connect(self._save_model)
        layout.addWidget(self.model_picker)

        form = QFormLayout()
        form.setSpacing(12)

        self.device_combo = QComboBox()
        for code in ("auto", "cuda", "cpu"):
            self.device_combo.addItem(tr(f"set.device.{code}"), code)
        _select_by_data(self.device_combo, self.config.device)
        self.device_combo.currentIndexChanged.connect(self._save_model)
        form.addRow(tr("set.device"), self.device_combo)

        layout.addLayout(form)
        layout.addSpacing(6)

        context_label = QLabel(tr("set.context_label"))
        context_label.setObjectName("muted")
        context_label.setToolTip(tr("set.context_tip"))
        layout.addWidget(context_label)
        self.context_edit = QPlainTextEdit(self.config.recognition_context)
        self.context_edit.setPlaceholderText(tr("set.context_ph"))
        self.context_edit.setFixedHeight(70)
        self.context_edit.textChanged.connect(self._save_context)
        self.context_edit.setToolTip(tr("set.context_tip"))
        layout.addWidget(self.context_edit)

        self.latency_btn = QPushButton(tr("set.latency_btn"))
        self.latency_btn.clicked.connect(self._run_latency_test)
        layout.addWidget(self.latency_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.latency_label = QLabel(tr("set.latency_hint"))
        self.latency_label.setWordWrap(True)
        self.latency_label.setObjectName("muted")
        layout.addWidget(self.latency_label)
        layout.addStretch()
        return page

    def _build_dictionary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.dict_hint_label = QLabel(
            tr("set.dict_hint") if self.config.replacements else tr("set.dict_empty")
        )
        self.dict_hint_label.setObjectName("muted")
        self.dict_hint_label.setWordWrap(True)
        layout.addWidget(self.dict_hint_label)

        self.dict_table = QTableWidget(0, 2)
        self.dict_table.setHorizontalHeaderLabels([tr("set.dict_heard"), tr("set.dict_written")])
        self.dict_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.dict_table.verticalHeader().setVisible(False)
        for heard, written in self.config.replacements.items():
            self._append_dict_row(heard, written)
        self.dict_table.itemChanged.connect(self._save_dictionary)
        layout.addWidget(self.dict_table, 1)

        buttons = QHBoxLayout()
        add_btn = QPushButton(tr("set.dict_add"))
        add_btn.clicked.connect(self._add_dict_row)
        remove_btn = QPushButton(tr("set.dict_remove"))
        remove_btn.clicked.connect(self._remove_dict_row)
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.keep_history_check = QCheckBox(tr("set.hist_keep"))
        self.keep_history_check.setChecked(self.config.keep_history)
        self.keep_history_check.toggled.connect(self._save_general)
        layout.addWidget(self.keep_history_check)

        self.history_list = QListWidget()
        self.history_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.history_list.setWordWrap(True)
        layout.addWidget(self.history_list, 1)

        buttons = QHBoxLayout()
        copy_btn = QPushButton(tr("set.hist_copy"))
        copy_btn.clicked.connect(self._copy_history_item)
        delete_btn = QPushButton(tr("set.hist_delete"))
        delete_btn.clicked.connect(self._delete_history_item)
        clear_btn = QPushButton(tr("set.hist_clear"))
        clear_btn.clicked.connect(self._clear_history)
        buttons.addWidget(copy_btn)
        buttons.addWidget(delete_btn)
        buttons.addWidget(clear_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.refresh_history()
        return page

    def _build_about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        title = QLabel(
            f'<span style="color:{theme.TEXT}">Parro</span>'
            f'<span style="color:{theme.ACCENT}">type</span>'
        )
        title.setObjectName("wordmark")   # Space Grotesk via app QSS
        layout.addWidget(title)

        slogan = QLabel(tr("set.about_slogan"))
        slogan.setObjectName("muted")
        layout.addWidget(slogan)
        layout.addSpacing(12)

        layout.addWidget(QLabel(tr("set.about_version", ver=APP_VERSION)))
        layout.addSpacing(12)

        privacy = QLabel(tr("set.about_local"))
        privacy.setWordWrap(True)
        layout.addWidget(privacy)

        if self.config.update_available_tag:
            update_label = QLabel(
                tr(
                    "set.about_update",
                    ver=self.config.update_available_tag.lstrip("vV"),
                    url=updates.RELEASES_PAGE_URL,
                )
            )
            update_label.setOpenExternalLinks(True)
            layout.addWidget(update_label)

        layout.addSpacing(8)
        self.updates_check = QCheckBox(tr("set.updates_cb"))
        self.updates_check.setChecked(self.config.check_updates)
        self.updates_check.toggled.connect(self._save_updates)
        layout.addWidget(self.updates_check)

        updates_note = QLabel(tr("set.updates_note"))
        updates_note.setObjectName("muted")
        updates_note.setWordWrap(True)
        layout.addWidget(updates_note)

        layout.addSpacing(12)
        free_line = QLabel(tr("set.about_free"))
        free_line.setWordWrap(True)
        layout.addWidget(free_line)
        layout.addSpacing(12)
        coffee_line = QLabel(tr("set.about_coffee"))
        coffee_line.setObjectName("muted")
        coffee_line.setWordWrap(True)
        layout.addWidget(coffee_line)
        coffee_btn = QPushButton(tr("set.about_coffee_btn"))   # plain button, NOT accent
        coffee_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://ko-fi.com/eugene_vovk"))
        )
        layout.addWidget(coffee_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    # -- persistence hooks ---------------------------------------------------

    def _save_hotkeys(self) -> None:
        ptt = self.ptt_edit.text().strip()
        toggle = self.toggle_edit.text().strip()
        if ptt and not validate_combo(ptt):
            self.ptt_edit.setStyleSheet(f"border: 1px solid {theme.REC};")
            return
        if toggle and not validate_combo(toggle):
            self.toggle_edit.setStyleSheet(f"border: 1px solid {theme.REC};")
            return
        self.ptt_edit.setStyleSheet("")
        self.toggle_edit.setStyleSheet("")
        self.config.hotkey_ptt = ptt
        self.config.hotkey_toggle = toggle
        self.config.save()
        self.config_changed.emit()

    def _save_general(self) -> None:
        self.config.language = self.lang_combo.currentData()
        self.config.ui_language = self.ui_lang_combo.currentData()
        self.config.insert_method = self.insert_combo.currentData()
        device_changed = self.config.input_device != self.mic_combo.currentData()
        self.config.input_device = self.mic_combo.currentData()
        self.config.autostart = self.autostart_check.isChecked()
        self.config.sound_ticks = self.sound_check.isChecked()
        self.config.keep_history = self.keep_history_check.isChecked()
        self.config.save()
        if device_changed:
            self._restart_monitor()
        self.config_changed.emit()

    def _save_model(self) -> None:
        self.config.model_size = self.model_picker.current
        self.config.device = self.device_combo.currentData()
        self.config.compute_type = "auto"
        self.config.save()
        self.config_changed.emit()

    def _save_updates(self) -> None:
        self.config.check_updates = self.updates_check.isChecked()
        self.config.save()
        self.config_changed.emit()

    def _save_context(self) -> None:
        self.config.recognition_context = self.context_edit.toPlainText()
        self.config.save()
        self.config_changed.emit()

    # -- dictionary -----------------------------------------------------------

    def _append_dict_row(self, heard: str, written: str) -> None:
        self.dict_table.blockSignals(True)
        row = self.dict_table.rowCount()
        self.dict_table.insertRow(row)
        self.dict_table.setItem(row, 0, QTableWidgetItem(heard))
        self.dict_table.setItem(row, 1, QTableWidgetItem(written))
        self.dict_table.blockSignals(False)

    def _add_dict_row(self) -> None:
        self._append_dict_row("", "")
        row = self.dict_table.rowCount() - 1
        self.dict_table.setCurrentCell(row, 0)
        self.dict_table.editItem(self.dict_table.item(row, 0))

    def _remove_dict_row(self) -> None:
        row = self.dict_table.currentRow()
        if row >= 0:
            self.dict_table.removeRow(row)
            self._save_dictionary()

    def _save_dictionary(self) -> None:
        replacements: dict[str, str] = {}
        for row in range(self.dict_table.rowCount()):
            heard_item = self.dict_table.item(row, 0)
            written_item = self.dict_table.item(row, 1)
            heard = heard_item.text().strip() if heard_item else ""
            written = written_item.text().strip() if written_item else ""
            if heard and written:
                replacements[heard] = written
        self.config.replacements = replacements
        self.dict_hint_label.setText(
            tr("set.dict_hint") if replacements else tr("set.dict_empty")
        )
        self.config.save()
        self.config_changed.emit()

    # -- history ----------------------------------------------------------------

    def refresh_history(self) -> None:
        from PySide6.QtGui import QBrush, QColor

        self.history_list.clear()
        if not self.history.entries:
            placeholder = QListWidgetItem(tr("set.hist_empty"))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            placeholder.setForeground(QBrush(QColor(theme.MUTED)))
            self.history_list.addItem(placeholder)
            return
        for entry in self.history.entries:
            stamp = time.strftime("%d.%m %H:%M", time.localtime(entry.timestamp))
            secs = f" · {entry.audio_seconds:.0f}s" if entry.audio_seconds else ""
            item = QListWidgetItem(f"[{stamp}{secs}] {entry.text}")
            item.setData(Qt.ItemDataRole.UserRole, entry.text)
            self.history_list.addItem(item)

    def _copy_history_item(self) -> None:
        item = self.history_list.currentItem()
        if item:
            QApplication.clipboard().setText(item.data(Qt.ItemDataRole.UserRole))

    def _delete_history_item(self) -> None:
        row = self.history_list.currentRow()
        if row >= 0:
            self.history.remove(row)
            self.refresh_history()

    def _clear_history(self) -> None:
        if (
            QMessageBox.question(
                self, tr("set.hist_clear_q_title"), tr("set.hist_clear_q")
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.history.clear()
            self.refresh_history()

    # -- latency test --------------------------------------------------------------

    def _run_latency_test(self) -> None:
        if not _TEST_WAV.exists():
            self.latency_label.setText(tr("set.latency_no_wav"))
            return
        self.latency_btn.setEnabled(False)
        self.latency_label.setText(tr("set.latency_running"))

        model = self.model_picker.current
        device = self.device_combo.currentData()

        def worker() -> None:
            try:
                cfg = Config.load()
                cfg.model_size = model
                cfg.device = device
                cfg.compute_type = "auto"
                engine = Engine(cfg)
                engine.load_model()
                engine.transcribe(str(_TEST_WAV))            # warm-up
                result = engine.transcribe(str(_TEST_WAV))   # measured run
                dev, _compute = cfg.resolve_device()
                msg = tr(
                    "set.latency_result",
                    model=model, dev="GPU" if dev == "cuda" else "CPU",
                    lat=f"{result.latency_seconds:.2f}",
                    dur=f"{result.audio_seconds:.0f}",
                )
                if result.latency_seconds < 1.5:
                    msg += tr("set.latency_fast")
                elif result.latency_seconds < 4:
                    msg += tr("set.latency_ok")
                else:
                    msg += tr("set.latency_slow")
            except Exception as exc:
                log.exception("Latency test failed")
                msg = tr("set.latency_error", err=exc)
            self._latency_done.emit(msg)

        threading.Thread(target=worker, daemon=True).start()

    def _show_latency_result(self, msg: str) -> None:
        self.latency_label.setText(msg)
        self.latency_btn.setEnabled(True)

    # -- style ------------------------------------------------------------------------

    def _apply_style(self) -> None:
        # Global app QSS covers widgets; only the dialog-specific chrome here.
        self.setStyleSheet(
            f"""
            QDialog {{ background: {theme.SURFACE}; }}
            QListWidget#sidebar {{
                background: #191920; border: none; border-radius: 0;
                border-right: 1px solid {theme.LINE}; padding-top: 12px;
            }}
            QListWidget#sidebar::item {{ padding: 10px 16px; border: none; border-radius: 0; }}
            QListWidget#sidebar::item:selected {{
                background: {theme.LINE}; color: {theme.ACCENT};
                border-left: 2px solid {theme.ACCENT};
            }}
            """
        )


def _select_by_data(combo: QComboBox, data) -> None:  # noqa: ANN001
    pos = combo.findData(data)
    if pos >= 0:
        combo.setCurrentIndex(pos)
