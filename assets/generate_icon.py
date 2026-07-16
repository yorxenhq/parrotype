"""Render the canonical mark (assets/logo.svg) into a multi-size ICO + PNG.

parrotype.ico frames: 16 (simplified variant), 32, 48, 256 (canon).
Run:  python assets/generate_icon.py     (needs dev deps: Pillow)
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from shells.tray.icons import make_pixmap  # noqa: E402


def _to_pil(size: int) -> Image.Image:
    pixmap = make_pixmap(size)
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    pixmap.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data())))


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed for the paint system
    assets = Path(__file__).resolve().parent

    _to_pil(256).save(assets / "parrotype.png")

    frames = [_to_pil(s) for s in (16, 32, 48, 256)]
    frames[-1].save(
        assets / "parrotype.ico",
        format="ICO",
        append_images=frames[:-1],
        sizes=[(16, 16), (32, 32), (48, 48), (256, 256)],
    )
    print("parrotype.ico (16/32/48/256) + parrotype.png written", file=sys.stderr)


if __name__ == "__main__":
    main()
