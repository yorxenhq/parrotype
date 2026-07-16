"""GPU offer panel: "NVIDIA present, runtime absent -> one-click enable".

Shared by the settings Model page and wizard step 2. Shows the honest
download size (queried from PyPI metadata, not guessed), a progress bar
during the download, and emits `installed` once the runtime is in place
and the hardware probes are re-primed.
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from core import cudasetup
from shells.tray.i18n import tr

log = logging.getLogger(__name__)


class GpuOfferPanel(QWidget):
    installed = Signal()          # runtime ready; probes re-primed
    _size_known = Signal(float)   # GB
    _progress = Signal(int)
    _finished = Signal(bool, str)  # ok, error text

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.note = QLabel(tr("gpu.offer_note"))
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.button = QPushButton(tr("gpu.offer_btn"))
        self.button.setObjectName("accent")
        self.button.clicked.connect(self._start_install)
        layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setFixedHeight(6)
        self.bar.hide()
        layout.addWidget(self.bar)

        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.status.hide()
        layout.addWidget(self.status)

        self._size_known.connect(self._on_size_known)
        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        self._busy = False
        self._fetch_size()

    # -- size label (exact bytes from PyPI, async) --------------------------

    def _fetch_size(self) -> None:
        def worker() -> None:
            try:
                self._size_known.emit(cudasetup.download_total_bytes() / 1e9)
            except Exception as exc:
                log.info("CUDA size query failed: %s", exc)

        threading.Thread(target=worker, daemon=True).start()

    def _on_size_known(self, gb: float) -> None:
        if not self._busy:
            self.button.setText(tr("gpu.offer_btn_size", size=f"{gb:.1f}"))

    # -- install -------------------------------------------------------------

    def _start_install(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.button.setEnabled(False)
        self.bar.setValue(0)
        self.bar.show()
        self.status.setText(tr("gpu.downloading", pct=0))
        self.status.show()

        def worker() -> None:
            try:
                cudasetup.install_cuda_runtime(progress_cb=self._progress.emit)
                self._finished.emit(True, "")
            except Exception as exc:
                log.exception("CUDA runtime install failed")
                self._finished.emit(False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_progress(self, pct: int) -> None:
        self.bar.setValue(pct)
        self.status.setText(
            tr("gpu.installing") if pct >= 99 else tr("gpu.downloading", pct=pct)
        )

    def _on_finished(self, ok: bool, error: str) -> None:
        self._busy = False
        self.bar.hide()
        if ok:
            self.note.hide()
            self.button.hide()
            self.status.setText(tr("gpu.done"))
            self.installed.emit()
        else:
            self.button.setEnabled(True)
            self.status.setText(tr("gpu.failed", err=error))
