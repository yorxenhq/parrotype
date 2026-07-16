"""Settings window: single dialog ~760x500 with left sidebar.

Pages: Общее / Модель / Словарь / История / О программе.
Quiet-tool style: no dashboards, no stats, no branding inside the UI.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
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

from core import APP_VERSION, Config, Engine, History, list_input_devices
from shells.tray import theme
from shells.tray.hotkeys import validate_combo

log = logging.getLogger(__name__)

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]
LANGUAGES = [("Auto", "auto"), ("Русский", "ru"), ("English", "en")]
DEVICES = [("Авто", "auto"), ("GPU (CUDA)", "cuda"), ("CPU", "cpu")]

_TEST_WAV = Path(__file__).resolve().parents[2] / "assets" / "latency_test.wav"


class SettingsDialog(QDialog):
    config_changed = Signal()
    visibility_changed = Signal(bool)   # True while the dialog is on screen
    _latency_done = Signal(str)

    def showEvent(self, event) -> None:  # noqa: N802, ANN001
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event) -> None:  # noqa: N802, ANN001
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    def __init__(self, config: Config, history: History, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.config = config
        self.history = history
        self.setWindowTitle("Parrotype — настройки")
        self.resize(760, 500)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(160)
        self.sidebar.setObjectName("sidebar")
        for name in ("Общее", "Модель", "Словарь", "История", "О программе"):
            QListWidgetItem(name, self.sidebar)

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
        self._apply_style()

    # -- pages -------------------------------------------------------------

    def _build_general_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)

        self.ptt_edit = QLineEdit(self.config.hotkey_ptt)
        self.ptt_edit.setPlaceholderText("например: ctrl+alt")
        self.ptt_edit.editingFinished.connect(self._save_hotkeys)
        form.addRow("Хоткей (удерживать):", self.ptt_edit)

        self.toggle_edit = QLineEdit(self.config.hotkey_toggle)
        self.toggle_edit.setPlaceholderText("например: ctrl+shift+space")
        self.toggle_edit.editingFinished.connect(self._save_hotkeys)
        form.addRow("Хоткей (вкл/выкл):", self.toggle_edit)

        self.lang_combo = QComboBox()
        for label, code in LANGUAGES:
            self.lang_combo.addItem(label, code)
        self.lang_combo.setCurrentIndex(
            next(
                (i for i, (_, c) in enumerate(LANGUAGES) if c == self.config.language),
                0,
            )
        )
        self.lang_combo.currentIndexChanged.connect(self._save_general)
        form.addRow("Язык:", self.lang_combo)

        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Системный по умолчанию", None)
        try:
            for idx, name in list_input_devices():
                self.mic_combo.addItem(name, idx)
        except Exception as exc:  # audio backend may be absent in CI
            log.error("Cannot list input devices: %s", exc)
        if self.config.input_device is not None:
            pos = self.mic_combo.findData(self.config.input_device)
            if pos >= 0:
                self.mic_combo.setCurrentIndex(pos)
        self.mic_combo.currentIndexChanged.connect(self._save_general)
        form.addRow("Микрофон:", self.mic_combo)

        self.insert_combo = QComboBox()
        self.insert_combo.addItem("Печать (быстро, не трогает буфер)", "auto")
        self.insert_combo.addItem("Через буфер обмена (совместимость)", "clipboard")
        pos = self.insert_combo.findData(self.config.insert_method)
        if pos >= 0:
            self.insert_combo.setCurrentIndex(pos)
        self.insert_combo.currentIndexChanged.connect(self._save_general)
        form.addRow("Способ вставки:", self.insert_combo)

        self.autostart_check = QCheckBox("Запускать вместе с Windows")
        self.autostart_check.setChecked(self.config.autostart)
        self.autostart_check.toggled.connect(self._save_general)
        form.addRow("Автозапуск:", self.autostart_check)

        self.sound_check = QCheckBox("Тихий тик старта/стопа записи")
        self.sound_check.setChecked(self.config.sound_ticks)
        self.sound_check.toggled.connect(self._save_general)
        form.addRow("Звук:", self.sound_check)

        return page

    def _build_model_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(12)

        self.model_combo = QComboBox()
        self.model_combo.addItems(MODEL_SIZES)
        if self.config.model_size in MODEL_SIZES:
            self.model_combo.setCurrentText(self.config.model_size)
        self.model_combo.currentIndexChanged.connect(self._save_model)
        form.addRow("Модель:", self.model_combo)

        self.device_combo = QComboBox()
        for label, code in DEVICES:
            self.device_combo.addItem(label, code)
        self.device_combo.setCurrentIndex(
            next((i for i, (_, c) in enumerate(DEVICES) if c == self.config.device), 0)
        )
        self.device_combo.currentIndexChanged.connect(self._save_model)
        form.addRow("Устройство:", self.device_combo)

        layout.addLayout(form)

        context_label = QLabel("Контекст распознавания (термины, имена — подсказка модели):")
        context_label.setObjectName("muted")
        layout.addWidget(context_label)
        self.context_edit = QPlainTextEdit(self.config.recognition_context)
        self.context_edit.setPlaceholderText(
            "Например: Claude Code, Cloudflare, Kubernetes…"
        )
        self.context_edit.setFixedHeight(70)
        self.context_edit.textChanged.connect(self._save_context)
        layout.addWidget(self.context_edit)

        self.latency_btn = QPushButton("Тест латентности")
        self.latency_btn.clicked.connect(self._run_latency_test)
        layout.addWidget(self.latency_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.latency_label = QLabel(
            "Замер на 10-сек аудио покажет реальную скорость выбранной модели."
        )
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

        hint = QLabel("Словарь замен: «слышу → пишу». Применяется после распознавания.")
        hint.setObjectName("muted")
        layout.addWidget(hint)

        self.dict_table = QTableWidget(0, 2)
        self.dict_table.setHorizontalHeaderLabels(["Слышу", "Пишу"])
        self.dict_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.dict_table.verticalHeader().setVisible(False)
        for heard, written in self.config.replacements.items():
            self._append_dict_row(heard, written)
        self.dict_table.itemChanged.connect(self._save_dictionary)
        layout.addWidget(self.dict_table, 1)

        buttons = QHBoxLayout()
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add_dict_row)
        remove_btn = QPushButton("Удалить строку")
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

        self.keep_history_check = QCheckBox("Хранить историю диктовок (локально)")
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
        copy_btn = QPushButton("Копировать")
        copy_btn.clicked.connect(self._copy_history_item)
        delete_btn = QPushButton("Удалить")
        delete_btn.clicked.connect(self._delete_history_item)
        clear_btn = QPushButton("Очистить всё")
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
        font = QFont(theme.FONT_UI, 16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        slogan = QLabel("You talk. The parrot types.")
        slogan.setObjectName("muted")
        layout.addWidget(slogan)

        layout.addWidget(QLabel(f"Версия {APP_VERSION}"))
        privacy = QLabel(
            "Всё работает локально: аудио и текст никуда не отправляются."
        )
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        layout.addStretch()
        return page

    # -- persistence hooks ---------------------------------------------------

    def _save_hotkeys(self) -> None:
        ptt = self.ptt_edit.text().strip()
        toggle = self.toggle_edit.text().strip()
        if ptt and not validate_combo(ptt):
            self.ptt_edit.setStyleSheet("border: 1px solid #FF5C5C;")
            return
        if toggle and not validate_combo(toggle):
            self.toggle_edit.setStyleSheet("border: 1px solid #FF5C5C;")
            return
        self.ptt_edit.setStyleSheet("")
        self.toggle_edit.setStyleSheet("")
        self.config.hotkey_ptt = ptt
        self.config.hotkey_toggle = toggle
        self.config.save()
        self.config_changed.emit()

    def _save_general(self) -> None:
        self.config.language = self.lang_combo.currentData()
        self.config.insert_method = self.insert_combo.currentData()
        self.config.input_device = self.mic_combo.currentData()
        self.config.autostart = self.autostart_check.isChecked()
        self.config.sound_ticks = self.sound_check.isChecked()
        self.config.keep_history = self.keep_history_check.isChecked()
        self.config.save()
        self.config_changed.emit()

    def _save_model(self) -> None:
        self.config.model_size = self.model_combo.currentText()
        self.config.device = self.device_combo.currentData()
        self.config.compute_type = "auto"
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
        # An appended empty row is invisible without focus — open the editor
        # on the "heard" cell immediately so the click has visible effect.
        self._append_dict_row("", "")
        row = self.dict_table.rowCount() - 1
        self.dict_table.setCurrentCell(row, 0)
        self.dict_table.setFocus()
        item = self.dict_table.item(row, 0)
        if item is not None:
            self.dict_table.editItem(item)

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
        self.config.save()
        self.config_changed.emit()

    # -- history ----------------------------------------------------------------

    def refresh_history(self) -> None:
        self.history_list.clear()
        for entry in self.history.entries:
            stamp = time.strftime("%d.%m %H:%M", time.localtime(entry.timestamp))
            secs = f" · {entry.audio_seconds:.0f}с" if entry.audio_seconds else ""
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
            QMessageBox.question(self, "История", "Удалить все записи истории?")
            == QMessageBox.StandardButton.Yes
        ):
            self.history.clear()
            self.refresh_history()

    # -- latency test --------------------------------------------------------------

    def _run_latency_test(self) -> None:
        if not _TEST_WAV.exists():
            self.latency_label.setText(
                "Тестовый файл assets/latency_test.wav не найден."
            )
            return
        self.latency_btn.setEnabled(False)
        self.latency_label.setText("Замеряю… (первый запуск скачивает модель)")

        model = self.model_combo.currentText()
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
                dev, compute = cfg.resolve_device()
                msg = (
                    f"{model} @ {dev} ({compute}): "
                    f"{result.latency_seconds:.2f}с на "
                    f"{result.audio_seconds:.0f}с аудио"
                )
                if result.latency_seconds < 1.5:
                    msg += " — на этой машине работает быстро."
                elif result.latency_seconds < 4:
                    msg += " — приемлемо."
                else:
                    msg += " — медленно, попробуйте модель меньше."
            except Exception as exc:  # surface any backend failure to the user
                log.exception("Latency test failed")
                msg = f"Ошибка теста: {exc}"
            self._latency_done.emit(msg)

        threading.Thread(target=worker, daemon=True).start()

    def _show_latency_result(self, msg: str) -> None:
        self.latency_label.setText(msg)
        self.latency_btn.setEnabled(True)

    # -- style ------------------------------------------------------------------------

    def _apply_style(self) -> None:
        scheme = QApplication.styleHints().colorScheme()
        dark = scheme != Qt.ColorScheme.Light   # dark-first
        if dark:
            self.setStyleSheet(
                f"""
                QDialog {{ background: {theme.SURFACE}; color: {theme.TEXT}; }}
                QWidget {{ color: {theme.TEXT}; font-family: "{theme.FONT_UI}", "{theme.FONT_UI_FALLBACK}"; }}
                QListWidget#sidebar {{
                    background: #191920; border: none;
                    border-right: 1px solid {theme.LINE}; padding-top: 12px;
                }}
                QListWidget#sidebar::item {{ padding: 10px 16px; border: none; }}
                QListWidget#sidebar::item:selected {{
                    background: {theme.LINE}; color: {theme.ACCENT};
                    border-left: 2px solid {theme.ACCENT};
                }}
                QLabel#muted {{ color: {theme.MUTED}; }}
                QLineEdit, QComboBox, QTableWidget, QListWidget, QPlainTextEdit {{
                    background: #17171C; border: 1px solid {theme.LINE};
                    border-radius: 6px; padding: 6px;
                }}
                QHeaderView::section {{
                    background: #191920; color: {theme.MUTED};
                    border: none; border-bottom: 1px solid {theme.LINE}; padding: 6px;
                }}
                QPushButton {{
                    background: {theme.LINE}; border: none; border-radius: 6px;
                    padding: 8px 16px;
                }}
                QPushButton:hover {{ background: #3A3A44; }}
                QPushButton:disabled {{ color: {theme.MUTED}; }}
                QCheckBox::indicator {{ width: 16px; height: 16px; }}
                """
            )
