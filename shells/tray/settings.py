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

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap, QTextLayout
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import APP_VERSION, Config, History, Recorder, list_input_devices
from core.config import cuda_available, cuda_usable
from core.history import HistoryEntry
from core.sttclient import EngineCrashed, IsolatedEngine
from core.sysprobe import summary_line
from shells.tray import icons, theme, updates
from shells.tray.gpupanel import GpuOfferPanel
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


# -- history cards -----------------------------------------------------------

_TRASH_SVG = """<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
<path d="M3 4.5h10M6.4 4.5V3.3c0-.5.4-.8.8-.8h1.6c.4 0 .8.3.8.8v1.2M4.6 4.5l.55 8.1c.04.6.54 1.1 1.15 1.1h3.4c.6 0 1.1-.5 1.15-1.1l.55-8.1M6.7 7v4M9.3 7v4"
 stroke="{color}" stroke-width="1.25" fill="none" stroke-linecap="round"/></svg>"""


def _trash_pixmap(color: str, size: int = 15) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(_TRASH_SVG.format(color=color).encode("utf-8"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return pixmap


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _format_meta(entry: HistoryEntry) -> str:
    """'14:03 · today · 12 s' — time, humanized day, audio length."""
    now = time.localtime()
    t = time.localtime(entry.timestamp)
    hhmm = time.strftime("%H:%M", t)
    yesterday = time.localtime(time.time() - 86400)
    if (t.tm_year, t.tm_yday) == (now.tm_year, now.tm_yday):
        day = tr("set.hist_today")
    elif (t.tm_year, t.tm_yday) == (yesterday.tm_year, yesterday.tm_yday):
        day = tr("set.hist_yesterday")
    else:
        day = time.strftime("%d.%m" if t.tm_year == now.tm_year else "%d.%m.%y", t)
    meta = f"{hhmm} · {day}"
    secs = int(entry.audio_seconds)
    if secs >= 60:
        meta += f" · {secs // 60}:{secs % 60:02d}"
    elif secs >= 1:
        meta += " · " + tr("set.hist_secs", n=secs)
    return meta


class _ClampLabel(QLabel):
    """Word-wrapped label clamped to N lines with a trailing ellipsis."""

    def __init__(self, text: str, lines: int = 3, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._full = text.replace("\n", " ").strip()
        self._lines = lines
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        super().setText(self._full)

    def resizeEvent(self, e) -> None:  # noqa: N802, ANN001
        super().resizeEvent(e)
        self._reclamp()

    def _reclamp(self) -> None:
        fm = self.fontMetrics()
        width = max(50, self.width())
        layout = QTextLayout(self._full, self.font())
        layout.beginLayout()
        text = self._full
        for i in range(self._lines):
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            if i == self._lines - 1 and line.textStart() + line.textLength() < len(self._full):
                last = self._full[line.textStart():]
                text = self._full[:line.textStart()] + fm.elidedText(
                    last, Qt.TextElideMode.ElideRight, width
                )
                break
        layout.endLayout()
        super().setText(text)


class HistoryCard(QFrame):
    """One dictation: meta row + clamped text. Click = copy, hover = trash."""

    copy_requested = Signal(object)     # self
    delete_requested = Signal(object)   # self

    def __init__(self, entry: HistoryEntry, index: int, scroll: QScrollArea, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.entry = entry
        self.index = index              # newest-first index — History.remove() contract
        self._scroll = scroll
        self._copied_timer: QTimer | None = None
        self.setObjectName("histcard")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 10, 12)
        v.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.meta = QLabel(_format_meta(entry))
        self.meta.setObjectName("histmeta")
        self.copied_label = QLabel(tr("set.hist_copied"))
        self.copied_label.setObjectName("histcopied")
        self.copied_label.hide()
        self.trash_btn = QToolButton()
        self.trash_btn.setObjectName("histtrash")
        self.trash_btn.setIcon(QIcon(_trash_pixmap(theme.MUTED)))
        self.trash_btn.setIconSize(QSize(15, 15))
        self.trash_btn.setToolTip(tr("set.hist_delete_tip"))
        self.trash_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.trash_btn.hide()
        self.trash_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        head.addWidget(self.meta)
        head.addStretch()
        head.addWidget(self.copied_label)
        head.addWidget(self.trash_btn)
        v.addLayout(head)
        self.body = _ClampLabel(entry.text, lines=3)
        v.addWidget(self.body)

    def enterEvent(self, e) -> None:  # noqa: N802, ANN001
        self.trash_btn.show()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802, ANN001
        self.trash_btn.hide()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802, ANN001
        # Click on the card = copy; the trash button consumes its own clicks.
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            e.position().toPoint()
        ):
            self.copy_requested.emit(self)
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802, ANN001
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.copy_requested.emit(self)
        elif e.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit(self)
        elif e.key() == Qt.Key.Key_Down:
            self.focusNextChild()
        elif e.key() == Qt.Key.Key_Up:
            self.focusPreviousChild()
        else:
            super().keyPressEvent(e)

    def focusInEvent(self, e) -> None:  # noqa: N802, ANN001
        super().focusInEvent(e)
        self._scroll.ensureWidgetVisible(self, 0, 8)

    def flash_copied(self) -> None:
        self.copied_label.show()
        self.setProperty("copied", True)
        _repolish(self)
        if self._copied_timer is not None:
            self._copied_timer.stop()
        self._copied_timer = QTimer(self)
        self._copied_timer.setSingleShot(True)
        self._copied_timer.timeout.connect(self._unflash)
        self._copied_timer.start(1200)

    def _unflash(self) -> None:
        self.copied_label.hide()
        self.setProperty("copied", False)
        _repolish(self)


class SettingsDialog(QDialog):
    config_changed = Signal()
    visibility_changed = Signal(bool)   # True while the dialog is on screen
    _latency_done = Signal(str)
    _level = Signal(float)
    _polish_pct = Signal(int)
    _polish_done = Signal(bool, str)    # ok, error text

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

        side = QWidget()
        side.setObjectName("sidebarwrap")
        side.setFixedWidth(160)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        self.sidebar = QListWidget()          # attr name is a contract (app.py)
        self.sidebar.setObjectName("sidebar")
        for key in ("general", "model", "dictionary", "history", "about"):
            QListWidgetItem(tr(f"set.nav.{key}"), self.sidebar)
        sv.addWidget(self.sidebar, 1)

        # Ghost mark + version at the bottom — quiet chrome, not a button.
        foot = QHBoxLayout()
        foot.setContentsMargins(16, 10, 12, 14)
        foot.setSpacing(8)
        logo = QLabel()
        # Full mark (with the eye = premium version), recolored to quiet grey
        # and dimmed to 45% — a signature, not a logo. Opacity is baked into
        # the pixmap (QGraphicsOpacityEffect is dropped by offscreen render).
        mark = icons.make_ghost_pixmap(28)
        ghost = QPixmap(mark.size())
        ghost.fill(Qt.GlobalColor.transparent)
        ghost_painter = QPainter(ghost)
        ghost_painter.setOpacity(0.45)
        ghost_painter.drawPixmap(0, 0, mark)
        ghost_painter.end()
        logo.setPixmap(ghost)
        ver = QLabel(APP_VERSION)
        ver.setObjectName("sideversion")
        foot.addWidget(logo)
        foot.addWidget(ver)
        foot.addStretch()
        sv.addLayout(foot)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_general_page())
        self.pages.addWidget(self._build_model_page())
        self.pages.addWidget(self._build_dictionary_page())
        self.pages.addWidget(self._build_history_page())
        self.pages.addWidget(self._build_about_page())

        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

        root.addWidget(side)
        root.addWidget(self.pages, 1)

        self._latency_done.connect(self._show_latency_result)
        self._polish_pct.connect(self._on_polish_pct)
        self._polish_done.connect(self._on_polish_done)
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
        self._model_page_layout = layout

        hw = summary_line()
        if hw:
            hw_label = QLabel(tr("model.machine", hw=hw))
            hw_label.setObjectName("muted")
            hw_label.setWordWrap(True)
            layout.addWidget(hw_label)

        # NVIDIA present but the CUDA runtime is not installed (the package
        # ships CPU-only): offer the one-click enable right where the user
        # is choosing speed/quality.
        if cuda_available() and not cuda_usable():
            self.gpu_panel: GpuOfferPanel | None = GpuOfferPanel()
            self.gpu_panel.installed.connect(self._on_gpu_installed)
            layout.addWidget(self.gpu_panel)
        else:
            self.gpu_panel = None

        self.model_picker = self._make_model_picker()
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

        layout.addSpacing(6)

        # -- polish: the local Wispr-style cleanup layer -----------------
        self.polish_check = QCheckBox(tr("set.polish_cb"))
        self.polish_check.setChecked(self.config.polish_enabled)
        self.polish_check.toggled.connect(self._on_polish_toggled)
        layout.addWidget(self.polish_check)

        self.polish_status = QLabel(tr("set.polish_hint"))
        self.polish_status.setObjectName("muted")
        self.polish_status.setWordWrap(True)
        layout.addWidget(self.polish_status)

        self.polish_bar = QProgressBar()
        self.polish_bar.setRange(0, 100)
        self.polish_bar.setFixedHeight(6)
        self.polish_bar.hide()
        layout.addWidget(self.polish_bar)

        layout.addSpacing(6)
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

        top = QHBoxLayout()
        self.keep_history_check = QCheckBox(tr("set.hist_keep"))
        self.keep_history_check.setChecked(self.config.keep_history)
        self.keep_history_check.toggled.connect(self._save_general)
        top.addWidget(self.keep_history_check)
        top.addStretch()

        self.clear_btn = QPushButton(tr("set.hist_clear"))
        self.clear_btn.clicked.connect(self._ask_clear)
        top.addWidget(self.clear_btn)

        # Inline confirmation instead of a QMessageBox — quieter.
        self.clear_confirm = QWidget()
        confirm_row = QHBoxLayout(self.clear_confirm)
        confirm_row.setContentsMargins(0, 0, 0, 0)
        confirm_row.setSpacing(8)
        confirm_label = QLabel(tr("set.hist_clear_confirm"))
        confirm_label.setObjectName("muted")
        yes_btn = QPushButton(tr("set.hist_clear_yes"))
        yes_btn.setObjectName("danger")
        yes_btn.clicked.connect(self._confirm_clear)
        no_btn = QPushButton(tr("set.hist_clear_no"))
        no_btn.clicked.connect(self._cancel_clear)
        confirm_row.addWidget(confirm_label)
        confirm_row.addWidget(yes_btn)
        confirm_row.addWidget(no_btn)
        self.clear_confirm.hide()
        top.addWidget(self.clear_confirm)
        layout.addLayout(top)

        self.hist_empty_label = QLabel(tr("set.hist_empty"))
        self.hist_empty_label.setObjectName("muted")
        self.hist_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hist_empty_label.setWordWrap(True)
        layout.addWidget(self.hist_empty_label, 1)

        self.hist_scroll = QScrollArea()
        self.hist_scroll.setWidgetResizable(True)
        self.hist_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.hist_scroll.setObjectName("histscroll")
        self._hist_container = QWidget()
        self._hist_vbox = QVBoxLayout(self._hist_container)
        self._hist_vbox.setContentsMargins(0, 0, 0, 0)
        self._hist_vbox.setSpacing(8)
        self._hist_vbox.addStretch(1)
        self.hist_scroll.setWidget(self._hist_container)
        layout.addWidget(self.hist_scroll, 1)

        self._clear_timer: QTimer | None = None
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
        # Full rebuild on every change: capped at 50 cards, cheap, and the
        # newest-first indices can never go stale.
        while self._hist_vbox.count() > 1:              # keep the trailing stretch
            item = self._hist_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        entries = self.history.entries                   # newest first
        self.hist_empty_label.setVisible(not entries)
        self.hist_scroll.setVisible(bool(entries))
        self.clear_btn.setEnabled(bool(entries))
        for i, entry in enumerate(entries):
            card = HistoryCard(entry, i, self.hist_scroll)
            card.copy_requested.connect(self._copy_card)
            card.delete_requested.connect(self._delete_card)
            self._hist_vbox.insertWidget(self._hist_vbox.count() - 1, card)

    def _copy_card(self, card: HistoryCard) -> None:
        QApplication.clipboard().setText(card.entry.text)
        card.flash_copied()

    def _delete_card(self, card: HistoryCard) -> None:
        self.history.remove(card.index)   # newest-first index — History.remove contract
        self.refresh_history()

    def _ask_clear(self) -> None:
        self.clear_btn.hide()
        self.clear_confirm.show()
        if self._clear_timer is not None:
            self._clear_timer.stop()
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self._cancel_clear)
        self._clear_timer.start(5000)     # auto-dismiss: no dangling confirm

    def _confirm_clear(self) -> None:
        self.history.clear()
        self.refresh_history()
        self._cancel_clear()

    def _cancel_clear(self) -> None:
        if self._clear_timer is not None:
            self._clear_timer.stop()
            self._clear_timer = None
        self.clear_confirm.hide()
        self.clear_btn.show()

    # -- model picker plumbing -------------------------------------------------

    def _make_model_picker(self) -> ModelPicker:
        options, note = machine_options(self.config.bench_results)
        if self.config.model_size not in {o.name for o in options}:
            # Hand-picked model outside the recommended trio (e.g. large-v3):
            # show it as a fourth card so the selection stays honest.
            size_n, size_unit = SIZES.get(self.config.model_size, ("—", "gb"))
            options = [
                *options,
                ModelOption(self.config.model_size, "model.desc.other",
                            "—", size_n, size_unit),
            ]
        picker = ModelPicker(options, self.config.model_size, note)
        picker.changed.connect(self._save_model)
        return picker

    def _rebuild_model_picker(self) -> None:
        """Swap the picker in place (bench numbers / GPU state changed)."""
        old = self.model_picker
        new = self._make_model_picker()
        index = self._model_page_layout.indexOf(old)
        self._model_page_layout.insertWidget(index, new)
        self._model_page_layout.removeWidget(old)
        old.deleteLater()
        self.model_picker = new

    def _on_gpu_installed(self) -> None:
        # Probes were re-primed by cudasetup; the picker set changes to the
        # GPU trio and config_changed lets the app restart its worker.
        self._rebuild_model_picker()
        self._save_model()

    # -- polish toggle -----------------------------------------------------------

    def _on_polish_toggled(self, checked: bool) -> None:
        if not checked:
            self.config.polish_enabled = False
            self.config.save()
            self.polish_status.setText(tr("set.polish_hint"))
            self.config_changed.emit()
            return
        from core.polish import PolishEngine

        polisher = PolishEngine(self.config.polish_model)
        if polisher.is_model_cached():
            self._enable_polish()
            return
        # First enable: fetch the model once, like the whisper weights.
        self.polish_check.setEnabled(False)
        self.polish_bar.setValue(0)
        self.polish_bar.show()
        self.polish_status.setText(tr("set.polish_downloading", pct=0))

        def worker() -> None:
            try:
                polisher.ensure_model(progress_cb=self._polish_pct.emit)
                self._polish_done.emit(True, "")
            except Exception as exc:
                log.exception("Polish model download failed")
                self._polish_done.emit(False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_polish_pct(self, pct: int) -> None:
        self.polish_bar.setValue(pct)
        self.polish_status.setText(tr("set.polish_downloading", pct=pct))

    def _on_polish_done(self, ok: bool, error: str) -> None:
        self.polish_check.setEnabled(True)
        self.polish_bar.hide()
        if ok:
            self._enable_polish()
        else:
            self.polish_check.blockSignals(True)
            self.polish_check.setChecked(False)
            self.polish_check.blockSignals(False)
            self.polish_status.setText(tr("set.polish_failed", err=error))

    def _enable_polish(self) -> None:
        self.config.polish_enabled = True
        self.config.save()
        self.polish_status.setText(tr("set.polish_ready"))
        self.config_changed.emit()

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
            # Bench runs in its OWN worker process (crash-safe): a model
            # that access-violates on this machine yields an honest
            # "unstable" verdict instead of taking the app down.
            from datetime import datetime, timezone

            overrides = {"model_size": model, "device": device,
                         "compute_type": "auto"}
            cfg = Config.load()
            for key, value in overrides.items():
                setattr(cfg, key, value)
            expected_dev, _ = cfg.resolve_device()
            engine = IsolatedEngine(cfg, overrides=overrides)
            stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            try:
                engine.ensure_model()
                engine.transcribe(str(_TEST_WAV))            # warm-up run
                result = engine.transcribe(str(_TEST_WAV))   # measured run
                dev = engine.actual_device or expected_dev
                self.config.bench_results[f"{model}|{dev}"] = {
                    "latency": round(result.latency_seconds, 2),
                    "audio": round(result.audio_seconds, 1),
                    "at": stamp,
                }
                self.config.save()
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
            except EngineCrashed:
                log.exception("Latency test: config is unstable on this machine")
                dev = engine.actual_device or expected_dev
                self.config.bench_results[f"{model}|{dev}"] = {
                    "unstable": True, "at": stamp,
                }
                self.config.save()
                msg = tr("set.latency_unstable", model=model)
            except Exception as exc:
                log.exception("Latency test failed")
                msg = tr("set.latency_error", err=exc)
            finally:
                engine.shutdown()
            self._latency_done.emit(msg)

        threading.Thread(target=worker, daemon=True).start()

    def _show_latency_result(self, msg: str) -> None:
        self.latency_label.setText(msg)
        self.latency_btn.setEnabled(True)
        self._rebuild_model_picker()   # show the fresh measured number

    # -- style ------------------------------------------------------------------------

    def _apply_style(self) -> None:
        # Global app QSS covers widgets; only the dialog-specific chrome here.
        self.setStyleSheet(
            f"""
            QDialog {{ background: {theme.SURFACE}; }}
            QWidget#sidebarwrap {{ background: #191920; border-right: 1px solid {theme.LINE}; }}
            QListWidget#sidebar {{ background: transparent; border: none; border-radius: 0; padding-top: 12px; }}
            QListWidget#sidebar::item {{ padding: 10px 16px; border: none; border-radius: 0; }}
            QListWidget#sidebar::item:selected {{
                background: {theme.LINE}; color: {theme.ACCENT};
                border-left: 2px solid {theme.ACCENT};
            }}
            QLabel#sideversion {{ color: #6B6B76; font-size: 11px; }}
            """
        )


def _select_by_data(combo: QComboBox, data) -> None:  # noqa: ANN001
    pos = combo.findData(data)
    if pos >= 0:
        combo.setCurrentIndex(pos)
