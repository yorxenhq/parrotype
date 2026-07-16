"""Render the canonical mark into assets/app.ico + parrotype.png.

app.ico frames: 16/32 (plaque + simplified logo-small mark — the eye
turns to mush at small sizes), 48/256 (assets/appicon.svg as-is).
Run:  python assets/generate_icon.py     (needs dev deps: Pillow)
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ASSETS = Path(__file__).resolve().parent


def _inner(svg_text: str) -> str:
    """Strip the outer <svg> wrapper, keep the drawing content."""
    return re.sub(r"^.*?<svg[^>]*>|</svg>\s*$", "", svg_text, flags=re.S)


def _appicon_svg(small: bool) -> str:
    if not small:
        return (ASSETS / "appicon.svg").read_text(encoding="utf-8")
    plaque = (
        '<rect x="3" y="3" width="90" height="90" rx="22" fill="#15151A"/>'
        '<rect x="3" y="3" width="90" height="90" rx="22" fill="none" '
        'stroke="#4FD1B0" stroke-width="2.5"/>'
    )
    mark = _inner((ASSETS / "logo-small.svg").read_text(encoding="utf-8"))
    return (
        '<svg viewBox="0 0 96 96" xmlns="http://www.w3.org/2000/svg">'
        f'{plaque}<g transform="translate(11,12) scale(0.78)">{mark}</g></svg>'
    )


def _render(svg: str, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(svg.encode("utf-8")).render(painter)
    painter.end()
    return pixmap


def _to_pil(pixmap: QPixmap) -> Image.Image:
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    pixmap.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data())))


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed for the paint system

    frames = {
        16: _to_pil(_render(_appicon_svg(small=True), 16)),
        32: _to_pil(_render(_appicon_svg(small=True), 32)),
        48: _to_pil(_render(_appicon_svg(small=False), 48)),
        256: _to_pil(_render(_appicon_svg(small=False), 256)),
    }
    frames[256].save(ASSETS / "parrotype.png")
    frames[256].save(
        ASSETS / "app.ico",
        format="ICO",
        append_images=[frames[16], frames[32], frames[48]],
        sizes=[(16, 16), (32, 32), (48, 48), (256, 256)],
    )
    print("app.ico (16/32/48/256) + parrotype.png written", file=sys.stderr)


if __name__ == "__main__":
    main()
