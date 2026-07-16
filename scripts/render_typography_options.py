"""Typography OPTIONS collage — for the owner to choose, nothing committed.

Three variants on real app renders (wordmark card + wizard step 1 + pill):
  A. Segoe UI Variable everywhere (current)
  B. Manrope for headings/wordmark (OFL, would be bundled), Segoe body
  C. Space Grotesk for headings/wordmark (OFL), Segoe body
Mono (Cascadia) unchanged in all variants.

Output: design/preview/typography-options.png (~1600px, Latin captions)
Run: python scripts/render_typography_options.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PARROTYPE_DATA_DIR", str(Path(os.environ.get("TEMP", ".")) / "parrotype_typo"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtCore import QBuffer, Qt  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

from core import Config  # noqa: E402
from shells.tray import theme  # noqa: E402
from shells.tray.i18n import set_language  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "design" / "preview"
FONTS = Path(__file__).resolve().parents[1] / "design" / "fonts"
BG = (16, 16, 20)

_app = QApplication(sys.argv)
theme.load_fonts()
_app.setStyleSheet(theme.app_qss())
set_language("ru")

for font_file in FONTS.glob("*.ttf"):
    QFontDatabase.addApplicationFont(str(font_file))

VARIANTS = [
    ("A — Segoe UI Variable (current)", None),
    ("B — Manrope headings + Segoe body", "Manrope"),
    ("C — Space Grotesk headings + Segoe body", "Space Grotesk"),
]


def _to_pil(pixmap) -> Image.Image:  # noqa: ANN001
    import io

    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    pixmap.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")


def _wordmark_card(heading_family: str | None) -> Image.Image:
    card = QWidget()
    card.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    card.setFixedSize(520, 150)
    card.setStyleSheet(f"background: {theme.SURFACE}; border-radius: 12px;")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(28, 24, 28, 24)

    family = heading_family or theme.FONT_UI
    title = QLabel(
        f'<span style="color:{theme.TEXT}">Parro</span>'
        f'<span style="color:{theme.ACCENT}">type</span>'
    )
    # Inline stylesheet: the app-wide QSS would override QFont otherwise.
    title.setStyleSheet(
        f"font-family: '{family}'; font-size: 40px; font-weight: 700; background: transparent;"
    )
    layout.addWidget(title)

    slogan = QLabel("You talk. The parrot types. · Настройки · Проверить скорость")
    slogan.setStyleSheet(
        f"color: {theme.MUTED}; font-size: 15px; font-family: '{family}'; background: transparent;"
    )
    layout.addWidget(slogan)
    return _to_pil(card.grab())


def _wizard_shot(heading_family: str | None) -> Image.Image:
    from shells.tray.wizard import FirstRunWizard

    wizard = FirstRunWizard(Config())
    wizard.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    family = heading_family or theme.FONT_UI
    # Same size in all variants for a fair comparison; family is the variable.
    wizard.setStyleSheet(
        wizard.styleSheet()
        + f"""
        QLabel#steptitle {{ font-family: '{family}'; font-size: 20px; font-weight: 700; }}
        QLabel#stepno {{ font-family: '{family}'; }}
        """
    )
    wizard.pages.setCurrentIndex(0)
    wizard.wiz_meter._level = 0.55
    _app.processEvents()
    shot = _to_pil(wizard.grab())
    wizard._stop_monitor()
    wizard.deleteLater()
    return shot


def _pill_shot() -> Image.Image:
    from shells.tray.overlay import OverlayPill

    pill = OverlayPill()
    pill.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    pill.show_listening("RU", toggle_mode=False)
    pill._heights = [0.28, 0.62, 0.95, 0.7, 0.4, 0.55, 0.8, 0.35,
                     0.6, 0.9, 0.5, 0.3, 0.66, 0.45]
    pill._elapsed_ms = 7000
    pill._anim.stop()
    pill._tick_timer.stop()
    pill._anim_t = 1.0
    shot = _to_pil(pill.grab())
    pill.deleteLater()
    return shot


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    cols = []
    pill = _pill_shot()   # identical across variants (no headings in the pill)
    for caption, family in VARIANTS:
        cols.append((caption, _wordmark_card(family), _wizard_shot(family)))

    pad = 30
    col_w = (1600 - pad * 4) // 3
    font_c = _font(24)
    font_t = _font(34)

    wiz_h = int(cols[0][2].height * (col_w / cols[0][2].width))
    card_h = int(cols[0][1].height * (col_w / cols[0][1].width))
    pill_scaled = pill.resize(
        (col_w, int(pill.height * (col_w / pill.width))), Image.LANCZOS
    )
    total_h = 120 + card_h + 16 + wiz_h + 16 + pill_scaled.height + 70

    canvas = Image.new("RGBA", (1600, total_h), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((48, 28), "Parrotype — typography options (pick one; nothing applied yet)",
              font=font_t, fill=(236, 236, 241))

    for i, (caption, card, wiz) in enumerate(cols):
        x = pad + i * (col_w + pad)
        y = 110
        canvas.alpha_composite(card.resize((col_w, card_h), Image.LANCZOS), (x, y))
        y += card_h + 16
        canvas.alpha_composite(wiz.resize((col_w, wiz_h), Image.LANCZOS), (x, y))
        y += wiz_h + 16
        canvas.alpha_composite(pill_scaled, (x, y))
        draw.text((x, y + pill_scaled.height + 12), caption, font=font_c, fill=(154, 154, 166))

    OUT.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUT / "typography-options.png")
    print(f"written {OUT / 'typography-options.png'}", file=sys.stderr)


if __name__ == "__main__":
    main()
