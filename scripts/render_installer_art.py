"""Render the branded Inno Setup wizard images (offscreen Qt, no screen).

Inno Setup takes classic BMPs:
  WizardImageFile      — left banner of the welcome/finish pages, 164x314
                         (plus a 200% variant for high-DPI, 328x628)
  WizardSmallImageFile — top-right mark on inner pages, 55x58 (+110x116)

Design: the quiet-premium brand look — near-black panel, the full parrot
mark (eye version — D-brand-2: premium form wherever readable), the
wordmark in the heading face, the two-dots-and-line signature in mint.

Run: python scripts/render_installer_art.py   -> assets/installer/*.bmp
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault(
    "PARROTYPE_DATA_DIR", str(Path(os.environ.get("TEMP", ".")) / "pt_installer_art")
)

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor, QFont, QImage, QPainter, QPen,
)
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "installer"

BG = QColor("#101014")          # tokens: bg/page — «фон витрин и глубоких поверхностей»
TEXT = QColor("#ECECF1")
MUTED = QColor("#9A9AA6")
ACCENT = QColor("#4FD1B0")


def _svg(path: Path) -> QSvgRenderer:
    renderer = QSvgRenderer(str(path))
    assert renderer.isValid(), path
    return renderer


def _signature(p: QPainter, cx: float, y: float, width: float, scale: float) -> None:
    """The brand signature: two dots and a line, in mint."""
    dot_r = 1.6 * scale
    gap = 7 * scale
    line_w = width - 2 * (dot_r * 2 + gap)
    left = cx - width / 2
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(ACCENT)
    p.drawEllipse(QRectF(left, y - dot_r, dot_r * 2, dot_r * 2))
    pen = QPen(ACCENT, max(1.0, 1.2 * scale))
    p.setPen(pen)
    p.drawLine(
        int(left + dot_r * 2 + gap), int(y),
        int(left + dot_r * 2 + gap + line_w), int(y),
    )
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(left + width - dot_r * 2, y - dot_r, dot_r * 2, dot_r * 2))


def render_banner(width: int, height: int, out: Path) -> None:
    scale = width / 164.0
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(BG)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    # mark (full version, with the eye)
    logo = _svg(ROOT / "assets" / "logo.svg")
    mark = 56 * scale
    logo.render(p, QRectF((width - mark) / 2, 64 * scale, mark, mark))

    # wordmark
    font = QFont("Space Grotesk")
    font.setPixelSize(int(19 * scale))
    font.setWeight(QFont.Weight.DemiBold)
    p.setFont(font)
    p.setPen(TEXT)
    p.drawText(
        QRectF(0, 136 * scale, width, 30 * scale),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        "Parrotype",
    )

    # slogan, quiet
    small = QFont("Segoe UI")
    small.setPixelSize(int(8.5 * scale))
    p.setFont(small)
    p.setPen(MUTED)
    p.drawText(
        QRectF(0, 162 * scale, width, 24 * scale),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        "You talk. The parrot types.",
    )

    # signature near the bottom
    _signature(p, width / 2, height - 34 * scale, 56 * scale, scale)

    p.end()
    img.save(str(out), "BMP")
    print("wrote", out, f"{width}x{height}")


def render_small(size_w: int, size_h: int, out: Path) -> None:
    img = QImage(size_w, size_h, QImage.Format.Format_RGB32)
    img.fill(BG)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    logo = _svg(ROOT / "assets" / "logo.svg")
    mark = min(size_w, size_h) * 0.68
    logo.render(
        p, QRectF((size_w - mark) / 2, (size_h - mark) / 2, mark, mark)
    )
    p.end()
    img.save(str(out), "BMP")
    print("wrote", out, f"{size_w}x{size_h}")


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 — QPainter/fonts need it
    from shells.tray import theme

    theme.load_fonts()            # Space Grotesk from assets/fonts
    OUT.mkdir(parents=True, exist_ok=True)
    render_banner(164, 314, OUT / "wizard-100.bmp")
    render_banner(328, 628, OUT / "wizard-200.bmp")
    render_small(55, 58, OUT / "wizard-small-100.bmp")
    render_small(110, 116, OUT / "wizard-small-200.bmp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
