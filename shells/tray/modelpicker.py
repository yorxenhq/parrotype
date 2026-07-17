"""Model picker: vertical radio-cards instead of a combo box.

Each card answers "how is this option different" in one human line;
the numbers (speed, download size) sit on the right, small. The device
(CPU/GPU) is said once, in a single muted note under the list.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.config import cuda_usable
from shells.tray.i18n import tr


@dataclass(frozen=True)
class ModelOption:
    name: str          # "small", "large-v3-turbo", ...
    desc_key: str      # i18n key of the human trade-off line
    sec: str           # "~N s per phrase" value, e.g. "0.8"; "—" = unmeasured
    size_n: str        # "1.6"
    size_unit: str     # "gb" | "mb"
    recommended: bool = False
    measured: bool = False    # sec is a real measurement on THIS machine
    unstable: bool = False    # the latency test crashed on this machine


GPU_OPTIONS = [
    ModelOption("large-v3-turbo", "model.desc.gpu.turbo",  "0.8", "1.6", "gb", recommended=True),
    ModelOption("medium",         "model.desc.gpu.medium", "0.9", "1.5", "gb"),
    ModelOption("small",          "model.desc.gpu.small",  "0.5", "460", "mb"),
]
CPU_OPTIONS = [
    ModelOption("small", "model.desc.cpu.small", "2.5", "460", "mb", recommended=True),
    ModelOption("base",  "model.desc.cpu.base",  "0.9", "140", "mb"),
    ModelOption("tiny",  "model.desc.cpu.tiny",  "0.5", "75",  "mb"),
]
# English-only whisper variants: same size and speed, trained purely on
# English — at tiny/base scale they hear English notably better than the
# multilingual builds. Offered when the user says they dictate English only.
EN_CPU_OPTIONS = [
    ModelOption("small.en", "model.desc.cpu.small", "2.5", "460", "mb", recommended=True),
    ModelOption("base.en",  "model.desc.cpu.base",  "0.9", "140", "mb"),
    ModelOption("tiny.en",  "model.desc.cpu.tiny",  "0.5", "75",  "mb"),
]

# Download sizes for every valid model (source: HF cache weights, matches
# the README "~75 MB tiny … ~3 GB large-v3" line).
SIZES: dict[str, tuple[str, str]] = {
    "tiny": ("75", "mb"),
    "base": ("140", "mb"),
    "small": ("460", "mb"),
    "medium": ("1.5", "gb"),
    "large-v3-turbo": ("1.6", "gb"),
    "large-v3": ("2.9", "gb"),
    "tiny.en": ("75", "mb"),
    "base.en": ("140", "mb"),
    "small.en": ("460", "mb"),
    "medium.en": ("1.5", "gb"),
}


def machine_options(
    bench: dict | None = None, language: str = "auto"
) -> tuple[list[ModelOption], str]:
    """The recommended option set + the one device note for this machine.

    bench — config.bench_results: hardcoded reference speeds are replaced
    by real measurements from THIS machine wherever the latency test ran.
    language — the recognition-language setting: "en" swaps the CPU set
    to the English-only .en builds (better English at the same size);
    the GPU set stays multilingual (large-v3-turbo is top-tier for
    English already, and at 0.8s there is nothing to trade).
    """
    if cuda_usable():
        options, note, device = GPU_OPTIONS, tr("model.device_note.gpu"), "cuda"
    elif language == "en":
        options, note, device = EN_CPU_OPTIONS, tr("model.device_note.cpu_en"), "cpu"
    else:
        options, note, device = CPU_OPTIONS, tr("model.device_note.cpu"), "cpu"
    if bench:
        options = [_apply_bench(opt, bench.get(f"{opt.name}|{device}"))
                   for opt in options]
    return options, note


def _apply_bench(opt: ModelOption, entry: dict | None) -> ModelOption:
    from dataclasses import replace

    if not entry:
        return opt
    if entry.get("unstable"):
        return replace(opt, unstable=True)
    latency = entry.get("latency")
    if latency is None:
        return opt
    return replace(opt, sec=f"{float(latency):.1f}", measured=True)


class ModelCard(QFrame):
    clicked = Signal(str)

    def __init__(self, opt: ModelOption, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.opt = opt
        self.setObjectName("modelcard")
        self.setProperty("selected", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(8)
        name = QLabel(opt.name)
        name.setObjectName("modelname")
        head.addWidget(name)
        if opt.recommended:
            chip = QLabel(tr("model.rec"))
            chip.setObjectName("recchip")
            head.addWidget(chip)
        head.addStretch()
        left.addLayout(head)
        desc = QLabel(tr(opt.desc_key))
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        left.addWidget(desc)
        row.addLayout(left, 1)

        lines = []
        if opt.unstable:
            lines.append(tr("model.meta.unstable"))
        elif opt.sec != "—":
            key = "model.meta.speed_measured" if opt.measured else "model.meta.speed"
            lines.append(tr(key, sec=opt.sec))
        if opt.size_n != "—":
            lines.append(tr(f"model.meta.size_{opt.size_unit}", n=opt.size_n))
        meta = QLabel("\n".join(lines))
        meta.setObjectName("modelmeta")
        meta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(meta)

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.clicked.emit(self.opt.name)


class ModelPicker(QWidget):
    """Vertical radio-cards for the model choice + one device note line."""

    changed = Signal(str)   # model name

    def __init__(self, options: list[ModelOption], selected: str,
                 device_note: str, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._cards: dict[str, ModelCard] = {}
        for opt in options:
            card = ModelCard(opt)
            card.clicked.connect(self.select)
            self._cards[opt.name] = card
            lay.addWidget(card)
        note = QLabel(device_note)
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addSpacing(2)
        lay.addWidget(note)
        self._current = ""
        self.select(selected if selected in self._cards else options[0].name,
                    emit=False)

    def select(self, name: str, emit: bool = True) -> None:
        if name == self._current:
            return
        self._current = name
        for n, card in self._cards.items():
            card.set_selected(n == name)
        if emit:
            self.changed.emit(name)

    @property
    def current(self) -> str:
        return self._current
