"""First-run wizard: microphone -> model -> hotkey + training dictation.

Three steps (spec §3.5), ~560x460, no mascot, no branding splash — the
wizard goes straight to business. Shown once (config.first_run_done).
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core import Config, Engine, Recorder, list_input_devices
from core.config import cuda_available, cuda_usable
from shells.tray import theme
from shells.tray.hotkeys import validate_combo
from shells.tray.i18n import tr
from shells.tray.native import enable_dark_titlebar
from shells.tray.settings import LevelMeter, _select_by_data

log = logging.getLogger(__name__)

_LEVEL_OK = 0.02      # RMS above this = "hearing you"


class FirstRunWizard(QDialog):
    finished_ok = Signal()
    model_available = Signal()   # weights on disk -> host app can load+warm now
    _level = Signal(float)
    _download_pct = Signal(int)
    _download_done = Signal(bool)

    def __init__(self, config: Config, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(tr("wiz.title"))
        self.setFixedSize(560, 470)

        self._monitor: Recorder | None = None
        self._heard_something = False
        self._downloading = False
        self._download_ok = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_mic_page())
        self.pages.addWidget(self._build_model_page())
        self.pages.addWidget(self._build_hotkey_page())
        root.addWidget(self.pages, 1)

        # footer: dots + back/next
        footer = QWidget()
        footer.setObjectName("wizfooter")
        flay = QHBoxLayout(footer)
        flay.setContentsMargins(20, 14, 20, 14)
        self.dots = QLabel()
        self.dots.setObjectName("muted")
        flay.addWidget(self.dots)
        flay.addStretch()
        self.back_btn = QPushButton(tr("wiz.back"))
        self.back_btn.clicked.connect(self._go_back)
        flay.addWidget(self.back_btn)
        self.next_btn = QPushButton(tr("wiz.next"))
        self.next_btn.setObjectName("accent")
        self.next_btn.clicked.connect(self._go_next)
        flay.addWidget(self.next_btn)
        root.addWidget(footer)

        self._level.connect(self._on_level)
        self._download_pct.connect(self._on_download_pct)
        self._download_done.connect(self._on_download_done)

        self.setStyleSheet(
            f"""
            QDialog {{ background: {theme.SURFACE}; }}
            QWidget#wizfooter {{ border-top: 1px solid {theme.LINE}; }}
            QLabel#stepno {{ color: {theme.ACCENT}; font-size: 11px; letter-spacing: 2px; }}
            QLabel#steptitle {{ font-size: 17px; font-weight: 600; }}
            QLabel#muted {{ color: {theme.MUTED}; }}
            QLabel#okline {{ color: {theme.ACCENT}; }}
            """
        )
        self._sync_footer()

    def showEvent(self, event) -> None:  # noqa: N802, ANN001
        super().showEvent(event)
        enable_dark_titlebar(self)
        QTimer.singleShot(150, self._enter_page)

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        self._stop_monitor()
        super().closeEvent(event)

    # -- pages -------------------------------------------------------------

    def _page_header(self, layout: QVBoxLayout, n: int, title: str, desc: str) -> None:
        step = QLabel(tr("wiz.step", n=n))
        step.setObjectName("stepno")
        layout.addWidget(step)
        title_label = QLabel(title)
        title_label.setObjectName("steptitle")
        layout.addWidget(title_label)
        desc_label = QLabel(desc)
        desc_label.setObjectName("muted")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        layout.addSpacing(10)

    def _build_mic_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 12)
        self._page_header(layout, 1, tr("wiz.mic.title"), tr("wiz.mic.desc"))

        self.mic_combo = QComboBox()
        try:
            for idx, name in list_input_devices(skip_virtual=True):
                self.mic_combo.addItem(name, idx)
        except Exception as exc:
            log.error("Cannot list input devices: %s", exc)
        if self.config.input_device is not None:
            _select_by_data(self.mic_combo, self.config.input_device)
        self.mic_combo.currentIndexChanged.connect(self._on_mic_changed)
        layout.addWidget(self.mic_combo)
        layout.addSpacing(14)

        self.wiz_meter = LevelMeter()
        self.wiz_meter.setFixedHeight(14)
        layout.addWidget(self.wiz_meter)
        layout.addSpacing(8)

        self.mic_status = QLabel(
            tr("wiz.mic.silent") if self.mic_combo.count() else tr("wiz.mic.none")
        )
        self.mic_status.setObjectName("muted")
        layout.addWidget(self.mic_status)
        layout.addStretch()

        # The one product promise, said once, where it matters most.
        local_note = QLabel(tr("wiz.mic.local_note"))
        local_note.setObjectName("muted")
        local_note.setWordWrap(True)
        layout.addWidget(local_note)
        return page

    def _build_model_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 12)
        self._page_header(layout, 2, tr("wiz.model.title"), tr("wiz.model.desc"))

        has_gpu = cuda_usable()
        gpu_blocked = cuda_available() and not has_gpu   # device present, libs missing
        recommended = "large-v3-turbo" if has_gpu else "small"
        options = (
            [("large-v3-turbo", "~0.8s"), ("medium", "~0.9s"), ("small", "~0.5s")]
            if has_gpu
            else [("small", "~2.5s"), ("base", "~0.9s"), ("tiny", "~0.5s")]
        )
        self.model_combo = QComboBox()
        rec_key = tr("wiz.model.rec_gpu") if has_gpu else tr("wiz.model.rec_cpu")
        for name, latency in options:
            label = f"{name}   ·  {latency}"
            if name == recommended:
                label += f"   —  {rec_key}"
            self.model_combo.addItem(label, name)
        self.model_combo.setCurrentIndex(0)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        layout.addWidget(self.model_combo)
        if gpu_blocked:
            # GPU detected but CUDA runtime libs are absent (e.g. packaged
            # CPU-only build): say so honestly instead of a silent fallback.
            gpu_note = QLabel(tr("wiz.model.gpu_missing_libs"))
            gpu_note.setObjectName("muted")
            gpu_note.setWordWrap(True)
            layout.addWidget(gpu_note)
        layout.addSpacing(16)

        self.dl_label = QLabel("")
        self.dl_label.setObjectName("muted")
        layout.addWidget(self.dl_label)
        self.dl_bar = QProgressBar()
        self.dl_bar.setRange(0, 100)
        self.dl_bar.setValue(0)
        self.dl_bar.setFixedHeight(6)
        self.dl_bar.hide()
        layout.addWidget(self.dl_bar)
        self.dl_retry_btn = QPushButton(tr("wiz.model.retry"))
        self.dl_retry_btn.clicked.connect(self._ensure_model)
        self.dl_retry_btn.hide()
        layout.addWidget(self.dl_retry_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    def _build_hotkey_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 12)
        self._page_header(layout, 3, tr("wiz.hotkey.title"), tr("wiz.hotkey.desc"))

        self.hotkey_edit = QLineEdit(self.config.hotkey_ptt)
        self.hotkey_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hotkey_edit.setStyleSheet(
            f"font-family: '{theme.FONT_MONO}'; font-size: 16px; color: {theme.ACCENT};"
            f"border: 1px dashed {theme.ACCENT}; padding: 10px;"
        )
        self.hotkey_edit.editingFinished.connect(self._save_hotkey)
        layout.addWidget(self.hotkey_edit)
        layout.addSpacing(14)

        try_label = QLabel(tr("wiz.hotkey.try"))
        try_label.setObjectName("muted")
        layout.addWidget(try_label)
        self.training_edit = QPlainTextEdit()
        self.training_edit.setFixedHeight(90)
        layout.addWidget(self.training_edit)
        layout.addStretch()
        return page

    # -- navigation ----------------------------------------------------------

    def _sync_footer(self) -> None:
        idx = self.pages.currentIndex()
        dots = "".join("●" if i <= idx else "○" for i in range(3))
        self.dots.setText(dots)
        self.back_btn.setVisible(idx > 0)
        self.next_btn.setText(tr("wiz.done") if idx == 2 else tr("wiz.next"))
        if idx == 1:
            self.next_btn.setEnabled(self._download_ok and not self._downloading)
        else:
            self.next_btn.setEnabled(True)

    def _go_back(self) -> None:
        if self.pages.currentIndex() > 0:
            self._leave_page()
            self.pages.setCurrentIndex(self.pages.currentIndex() - 1)
            self._enter_page()

    def _go_next(self) -> None:
        idx = self.pages.currentIndex()
        if idx == 2:
            self._finish()
            return
        self._leave_page()
        self.pages.setCurrentIndex(idx + 1)
        self._enter_page()

    def _enter_page(self) -> None:
        idx = self.pages.currentIndex()
        if idx == 0:
            self._start_monitor()
        elif idx == 1:
            self._ensure_model()
        self._sync_footer()

    def _leave_page(self) -> None:
        if self.pages.currentIndex() == 0:
            self._stop_monitor()

    def _finish(self) -> None:
        self._stop_monitor()
        self.config.first_run_done = True
        self.config.save()
        self.finished_ok.emit()
        self.accept()

    # -- step 1: microphone ----------------------------------------------------

    def _start_monitor(self) -> None:
        if self._monitor is not None:
            return
        try:
            self._monitor = Recorder(
                sample_rate=self.config.sample_rate,
                device=self.mic_combo.currentData(),
                on_level=self._level.emit,
            )
            self._monitor.start()
        except Exception as exc:
            log.warning("Wizard mic monitor failed: %s", exc)
            self._monitor = None

    def _stop_monitor(self) -> None:
        if self._monitor is not None:
            try:
                self._monitor.cancel()
            finally:
                self._monitor = None

    def _on_mic_changed(self) -> None:
        self.config.input_device = self.mic_combo.currentData()
        self.config.save()
        self._heard_something = False
        self.mic_status.setText(tr("wiz.mic.silent"))
        self.mic_status.setObjectName("muted")
        self.mic_status.setStyleSheet("")
        self._stop_monitor()
        self._start_monitor()

    def _on_level(self, rms: float) -> None:
        self.wiz_meter.push(rms)
        if not self._heard_something and rms > _LEVEL_OK:
            self._heard_something = True
            self.mic_status.setText(tr("wiz.mic.ok"))
            self.mic_status.setObjectName("okline")
            self.mic_status.setStyleSheet(f"color: {theme.ACCENT};")

    # -- step 2: model -----------------------------------------------------------

    def _on_model_changed(self) -> None:
        self.config.model_size = self.model_combo.currentData()
        self.config.save()
        self._ensure_model()

    def _ensure_model(self) -> None:
        if self._downloading:
            return
        self.config.model_size = self.model_combo.currentData()
        engine = Engine(self.config)
        if engine.is_model_cached():
            self._download_ok = True
            self.dl_bar.hide()
            self.dl_retry_btn.hide()
            self.dl_label.setText(tr("wiz.model.cached"))
            self._sync_footer()
            self.model_available.emit()
            return
        self._download_ok = False
        self._downloading = True
        self.dl_retry_btn.hide()
        self.dl_bar.setValue(0)
        self.dl_bar.show()
        self.dl_label.setText(tr("wiz.model.downloading", pct=0))
        self._sync_footer()

        def worker() -> None:
            try:
                engine.ensure_model(progress_cb=self._download_pct.emit)
                self._download_done.emit(True)
            except Exception:
                log.exception("Wizard model download failed")
                self._download_done.emit(False)

        threading.Thread(target=worker, daemon=True).start()

    def _on_download_pct(self, pct: int) -> None:
        self.dl_bar.setValue(pct)
        self.dl_label.setText(tr("wiz.model.downloading", pct=pct))

    def _on_download_done(self, ok: bool) -> None:
        self._downloading = False
        self._download_ok = ok
        if ok:
            self.dl_bar.setValue(100)
            self.dl_label.setText(tr("wiz.model.cached"))
            self.model_available.emit()
        else:
            self.dl_bar.hide()
            self.dl_label.setText(tr("wiz.model.failed"))
            self.dl_retry_btn.show()
        self._sync_footer()

    # -- step 3: hotkey ------------------------------------------------------------

    def _save_hotkey(self) -> None:
        combo = self.hotkey_edit.text().strip()
        if combo and validate_combo(combo):
            self.config.hotkey_ptt = combo
            self.config.save()
            self.hotkey_edit.setStyleSheet(
                f"font-family: '{theme.FONT_MONO}'; font-size: 16px; color: {theme.ACCENT};"
                f"border: 1px dashed {theme.ACCENT}; padding: 10px;"
            )
        else:
            self.hotkey_edit.setStyleSheet(
                f"font-family: '{theme.FONT_MONO}'; font-size: 16px; color: {theme.REC};"
                f"border: 1px dashed {theme.REC}; padding: 10px;"
            )
