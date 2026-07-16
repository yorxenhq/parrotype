"""Render the social preview / og:image (1280x640) with PySide6.

Composition (spec): quiet #101014 field, the canonical mark from
assets/logo.svg (rendered verbatim via QSvgRenderer, never redrawn),
wordmark + slogan + "local · free · offline" with accent status dots.
Rendered at 2x (2560x1280) and downscaled for crisp text.

Output: docs/site/og.png (og:image of every page) and
        docs/social-preview.png (upload by hand: GitHub -> Settings ->
        Social preview).

Run: python scripts/render_og.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QImage,
    QPainter,
)
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "assets" / "logo.svg"
FONT = ROOT / "design" / "fonts" / "SpaceGrotesk[wght].ttf"

W, H = 1280, 640
S = 2                      # supersampling factor

BG = "#101014"
TEXT = "#ECECF1"
MUTED = "#9A9AA6"
ACCENT = "#4FD1B0"


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841 — needed for font/paint machinery
    QFontDatabase.addApplicationFont(str(FONT))

    img = QImage(W * S, H * S, QImage.Format.Format_ARGB32)
    img.fill(QColor(BG))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Mark: verbatim assets/logo.svg, height ~380 at 1x, left edge x=120,
    # vertically centered on y=320.
    renderer = QSvgRenderer(str(LOGO))
    mark_h = 380 * S
    mark_w = mark_h                     # the mark's viewBox is square (96x96)
    renderer.render(p, QRectF(120 * S, (320 * S) - mark_h / 2, mark_w, mark_h))

    # Text block, left-aligned at x=600, grouped around the vertical center.
    x = 600 * S
    wordmark_font = QFont("Space Grotesk")
    wordmark_font.setPixelSize(104 * S)
    wordmark_font.setWeight(QFont.Weight.Medium)
    slogan_font = QFont("Space Grotesk")
    slogan_font.setPixelSize(42 * S)
    tag_font = QFont("Space Grotesk")
    tag_font.setPixelSize(32 * S)

    wm = QFontMetrics(wordmark_font)
    sm = QFontMetrics(slogan_font)
    tm = QFontMetrics(tag_font)

    gap1, gap2 = 28 * S, 36 * S
    block_h = wm.ascent() + wm.descent() + gap1 + sm.ascent() + sm.descent() + gap2 + tm.ascent() + tm.descent()
    y = (H * S - block_h) / 2 + wm.ascent()

    p.setFont(wordmark_font)
    p.setPen(QColor(TEXT))
    p.drawText(int(x), int(y), "Parrotype")

    y += wm.descent() + gap1 + sm.ascent()
    p.setFont(slogan_font)
    p.drawText(int(x), int(y), "You talk. The parrot types.")

    y += sm.descent() + gap2 + tm.ascent()
    p.setFont(tag_font)
    p.setPen(QColor(MUTED))
    dot_r = 4 * S                       # 8 px dots at 1x — brand status dots
    dot_gap = 22 * S
    cx = x
    for i, word in enumerate(("local", "free", "offline")):
        if i:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawEllipse(
                QRectF(cx + dot_gap - dot_r, y - tm.ascent() / 2 + tm.descent() - dot_r, dot_r * 2, dot_r * 2)
            )
            cx += dot_gap * 2
            p.setPen(QColor(MUTED))
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawText(int(cx), int(y), word)
        cx += tm.horizontalAdvance(word)
    p.end()

    final = img.scaled(
        W, H,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    for out in (ROOT / "docs" / "site" / "og.png", ROOT / "docs" / "social-preview.png"):
        final.save(str(out), "PNG")
        print(f"written {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
