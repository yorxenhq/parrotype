"""Render tray-icon states at real pixel sizes into design/preview/.

Output: tray-{idle,rec,paused}-{16,32}.png + a combined strip
tray-states.png (16px states side by side at 1x — what the taskbar shows).
Run: python scripts/render_tray_previews.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap  # noqa: E402

from shells.tray.icons import TrayState, make_pixmap  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "design" / "preview"

STATES = {
    "idle": TrayState.IDLE,
    "rec": TrayState.RECORDING,
    "paused": TrayState.PAUSED,
}


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841
    OUT.mkdir(parents=True, exist_ok=True)

    for name, state in STATES.items():
        for size in (16, 32):
            make_pixmap(size, state).save(str(OUT / f"tray-{name}-{size}.png"), "PNG")

    # Combined strip: the three 16px states on a dark taskbar-like band.
    strip = QPixmap(3 * 28 + 8, 28)
    strip.fill(Qt.GlobalColor.transparent)
    painter = QPainter(strip)
    painter.fillRect(strip.rect(), 0xFF17171C)
    for i, state in enumerate(STATES.values()):
        painter.drawPixmap(10 + i * 28, 6, make_pixmap(16, state))
    painter.end()
    strip.save(str(OUT / "tray-states.png"), "PNG")
    print(f"previews written to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
