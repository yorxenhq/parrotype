"""App/tray icon rendered from the canonical mascot mark (assets/logo.svg).

The mascot lives ONLY in the tray icon, app icon and the About page —
inside working UI screens the style stays strict, no mascot.

Tray rules:
  - 16 px: simplified mark (thicker light outline, no eye)
  - recording: red badge circle, top-right
  - paused: whole mark in muted grey
"""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from shells.tray import theme

_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo.svg"

# Embedded copy of the canonical mark (fallback when assets/ is not shipped).
_LOGO_SVG = """<svg width="96" height="96" viewBox="0 0 96 96" xmlns="http://www.w3.org/2000/svg">
  <rect x="34" y="14" width="7" height="18" rx="3.5" fill="#4FD1B0"/>
  <rect x="45" y="6"  width="7" height="26" rx="3.5" fill="#4FD1B0"/>
  <rect x="56" y="16" width="7" height="16" rx="3.5" fill="#4FD1B0"/>
  <path d="M28 58 C28 40 40 30 52 30 C66 30 76 41 76 55 C76 70 65 82 48 82 L36 82 C31 82 28 78 28 72 Z" fill="#1E1E24" stroke="#4FD1B0" stroke-width="3"/>
  <path d="M74 48 C84 50 86 58 80 63 C77 66 72 66 69 63 C73 59 74 54 74 48 Z" fill="#4FD1B0"/>
  <circle cx="56" cy="50" r="5" fill="#ECECF1"/>
  <circle cx="57.5" cy="50" r="2.4" fill="#101014"/>
</svg>"""

# 16 px simplification: thicker light outline, no eye; crest + beak stay.
_LOGO_SVG_SMALL = """<svg width="96" height="96" viewBox="0 0 96 96" xmlns="http://www.w3.org/2000/svg">
  <rect x="34" y="14" width="7" height="18" rx="3.5" fill="#4FD1B0"/>
  <rect x="45" y="6"  width="7" height="26" rx="3.5" fill="#4FD1B0"/>
  <rect x="56" y="16" width="7" height="16" rx="3.5" fill="#4FD1B0"/>
  <path d="M28 58 C28 40 40 30 52 30 C66 30 76 41 76 55 C76 70 65 82 48 82 L36 82 C31 82 28 78 28 72 Z" fill="#1E1E24" stroke="#ECECF1" stroke-width="6"/>
  <path d="M74 48 C84 50 86 58 80 63 C77 66 72 66 69 63 C73 59 74 54 74 48 Z" fill="#4FD1B0"/>
</svg>"""

_ACCENT_COLORS = (theme.ACCENT, "#ECECF1", "#101014")


class TrayState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PAUSED = auto()


def _canon_svg() -> str:
    if _LOGO_PATH.exists():
        try:
            return _LOGO_PATH.read_text(encoding="utf-8")
        except OSError:
            pass
    return _LOGO_SVG


def _svg_for(size: int, state: TrayState) -> bytes:
    svg = _LOGO_SVG_SMALL if size <= 20 else _canon_svg()
    if state == TrayState.PAUSED:
        for color in _ACCENT_COLORS:
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


def make_icon(state: TrayState = TrayState.IDLE) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 256):
        icon.addPixmap(make_pixmap(size, state))
    return icon
