"""App/tray icon rendered from the canonical mark (assets/logo*.svg).

Canon ("bar-parrot", clean baseline): a waveform whose third bar rises
into a round head with a dot eye — the recognition wave IS the bird.
No beak, no crest. Two variants:
  - logo.svg        mark with the eye — sizes >= 48px, About, brand
  - logo-small.svg  same without the eye — tray sizes 16-32px

Tray states:
  - idle:      mint mark
  - recording: mint mark + red badge circle, top-right
  - paused:    whole mark in muted grey

The mascot lives ONLY in the tray/app icon and the About page — inside
working UI screens the style stays strict, no mascot.
"""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from shells.tray import theme

_ASSETS = Path(__file__).resolve().parents[2] / "assets"

# Embedded copies of the canonical marks (fallback when assets/ is not shipped).
_LOGO_SVG = """<svg viewBox="0 0 96 96" xmlns="http://www.w3.org/2000/svg">
<rect x="20" y="42" width="10" height="32" rx="5" fill="#4FD1B0"/>
<rect x="34" y="28" width="10" height="46" rx="5" fill="#4FD1B0"/>
<path d="M48 74 L48 25 C48 16 54.8 10 63 10 C71.5 10 78 16.5 78 25 C78 33.5 71.5 40 63 40 L58 40 L58 74 C58 76.8 55.8 79 53 79 C50.2 79 48 76.8 48 74 Z" fill="#4FD1B0"/>
<circle cx="64" cy="23.5" r="3.6" fill="#101014"/></svg>"""

_LOGO_SMALL_SVG = """<svg viewBox="0 0 96 96" xmlns="http://www.w3.org/2000/svg">
<rect x="20" y="42" width="10" height="32" rx="5" fill="#4FD1B0"/>
<rect x="34" y="28" width="10" height="46" rx="5" fill="#4FD1B0"/>
<path d="M48 74 L48 25 C48 16 54.8 10 63 10 C71.5 10 78 16.5 78 25 C78 33.5 71.5 40 63 40 L58 40 L58 74 C58 76.8 55.8 79 53 79 C50.2 79 48 76.8 48 74 Z" fill="#4FD1B0"/></svg>"""

_MARK_COLORS = (theme.ACCENT,)   # recolored to muted when paused


class TrayState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PAUSED = auto()


def _read_svg(name: str, fallback: str) -> str:
    path = _ASSETS / name
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            pass
    return fallback


def _svg_for(size: int, state: TrayState) -> bytes:
    # Rule: full mark >= 48px, simplified variant for 16-32px.
    if size >= 48:
        svg = _read_svg("logo.svg", _LOGO_SVG)
    else:
        svg = _read_svg("logo-small.svg", _LOGO_SMALL_SVG)
    if state == TrayState.PAUSED:
        for color in _MARK_COLORS:
            svg = svg.replace(color, theme.MUTED)
    return svg.encode("utf-8")


def make_pixmap(size: int, state: TrayState = TrayState.IDLE) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(_svg_for(size, state))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    if state == TrayState.RECORDING:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.REC))
        r = size * 0.17
        painter.drawEllipse(QPointF(size - r - 1, r + 1), r, r)
    painter.end()
    return pixmap


def make_ghost_pixmap(size: int, mark: str = "#6B6B76", eye_bg: str = "#191920") -> QPixmap:
    """The full mark (with the eye) recolored as quiet chrome — used for the
    settings sidebar footer. The eye is a hole, so it takes the panel colour."""
    svg = _read_svg("logo.svg", _LOGO_SVG)
    svg = svg.replace(theme.ACCENT, mark).replace("#101014", eye_bg)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(svg.encode("utf-8"))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def make_icon(state: TrayState = TrayState.IDLE) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 256):
        icon.addPixmap(make_pixmap(size, state))
    return icon
