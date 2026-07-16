"""Render real app UI (QWidget.grab, offscreen) into large collages.

No screen capture, no desktop interaction: widgets are rendered on the
offscreen Qt platform, so the user's PC is untouched. Captions are Latin
(PIL font rendering; offscreen font stacks lose Cyrillic).

Output (design/preview/):
  pill-states.png    all pill states, current build vs v1 baseline
  settings-tabs.png  settings window, all five tabs
  wizard-steps.png   first-run wizard, three steps
  tray-menu.png      styled tray context menu

Run: python scripts/render_ui_previews.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PARROTYPE_DATA_DIR", str(Path(os.environ.get("TEMP", ".")) / "parrotype_preview"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtCore import QBuffer, Qt  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

# Real Windows platform for proper font shaping, but widgets are never
# mapped to the screen: WA_DontShowOnScreen renders them off-screen.


def _hide_from_screen(widget) -> None:  # noqa: ANN001
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

from core import Config, History  # noqa: E402
from shells.tray import theme  # noqa: E402
from shells.tray.i18n import set_language, tr  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "design" / "preview"
BG = (16, 16, 20)
CAPTION = (154, 154, 166)
TITLE = (236, 236, 241)

_app = QApplication(sys.argv)
_app.setStyleSheet(theme.app_qss())
set_language("ru")


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _to_pil(pixmap) -> Image.Image:  # noqa: ANN001
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    pixmap.save(buffer, "PNG")
    import io

    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")


def _grab(widget) -> Image.Image:  # noqa: ANN001
    return _to_pil(widget.grab())


# -- pill states ------------------------------------------------------------


def _make_pill(state: str):  # noqa: ANN001
    from shells.tray.overlay import OverlayPill

    pill = OverlayPill()
    _hide_from_screen(pill)
    demo_levels = [0.28, 0.62, 0.95, 0.7, 0.4, 0.55, 0.8, 0.35,
                   0.6, 0.9, 0.5, 0.3, 0.66, 0.45]
    if state == "listening":
        pill.show_listening("RU", toggle_mode=False)
        pill._heights = demo_levels
        pill._elapsed_ms = 7000
    elif state == "toggle":
        pill.show_listening("AUTO", toggle_mode=True)
        pill._heights = list(reversed(demo_levels))
        pill._elapsed_ms = 91000
    elif state == "transcribing":
        pill.show_transcribing()
    elif state == "status":
        pill.show_status(tr("pill.downloading_model", pct=62))
    elif state == "inserted":
        pill.show_inserted("Привет, собери отчёт по проекту и отправь его в чат")
    elif state == "error":
        pill.show_error(tr("pill.insert_failed"))
    pill._anim.stop()
    pill._tick_timer.stop()
    pill._anim_t = 1.0
    return pill


def render_pill_states() -> Image.Image:
    states = [
        ("listening", "Listening (push-to-talk, 0:07)"),
        ("toggle", "Listening (toggle, 1:31 -> accent timer)"),
        ("transcribing", "Transcribing"),
        ("status", "Model download progress"),
        ("inserted", "Inserted (flash, then fades)"),
        ("error", "Error (persistent, clickable)"),
    ]
    shots = []
    for key, caption in states:
        pill = _make_pill(key)
        shots.append((caption, _grab(pill)))
        pill.deleteLater()

    scale = 2.0
    font_c = _font(26)
    font_t = _font(34)
    row_h = max(int(img.height * scale) for _, img in shots) + 52
    width = 1600
    canvas = Image.new("RGBA", (width, 90 + row_h * len(shots)), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((48, 28), "Parrotype — overlay pill states (real app render)", font=font_t, fill=TITLE)
    y = 90
    for caption, img in shots:
        big = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        canvas.alpha_composite(big, ((width - big.width) // 2, y))
        draw.text((48, y + big.height - 4), caption, font=font_c, fill=CAPTION)
        y += row_h
    return canvas


# -- settings tabs -------------------------------------------------------------


def render_settings() -> Image.Image:
    from shells.tray.settings import SettingsDialog

    config = Config()
    history = History(limit=50)
    history.add("Привет, собери отчёт по проекту", 4.2)
    history.add("Deploy the worker on Cloudflare and restart the pipeline", 6.0)
    config.replacements = {"клод": "Claude", "кубер": "Kubernetes"}

    dialog = SettingsDialog(config, history)
    _hide_from_screen(dialog)
    dialog.resize(760, 500)
    tabs = ["General", "Model", "Dictionary", "History", "About"]
    shots = []
    for i, name in enumerate(tabs):
        dialog.sidebar.setCurrentRow(i)
        _app.processEvents()
        shots.append((name, _grab(dialog)))
    dialog.deleteLater()

    cols = 2
    pad = 40
    cell_w = (1600 - pad * 3) // cols
    scale = cell_w / shots[0][1].width
    cell_h = int(shots[0][1].height * scale) + 56
    rows = (len(shots) + cols - 1) // cols
    font_c = _font(26)
    font_t = _font(34)
    canvas = Image.new("RGBA", (1600, 100 + rows * (cell_h + pad)), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((48, 28), "Parrotype — settings window, all tabs (real app render)", font=font_t, fill=TITLE)
    for i, (name, img) in enumerate(shots):
        col, row = i % cols, i // cols
        x = pad + col * (cell_w + pad)
        y = 100 + row * (cell_h + pad)
        big = img.resize((cell_w, int(img.height * scale)), Image.LANCZOS)
        canvas.alpha_composite(big, (x, y))
        draw.text((x, y + big.height + 8), name, font=font_c, fill=CAPTION)
    return canvas


# -- wizard steps ---------------------------------------------------------------


def render_wizard() -> Image.Image:
    from shells.tray.wizard import FirstRunWizard

    config = Config()
    wizard = FirstRunWizard(config)
    _hide_from_screen(wizard)
    shots = []
    captions = ["Step 1 — Microphone + live level", "Step 2 — Model + download", "Step 3 — Hotkey + training"]
    for i, caption in enumerate(captions):
        wizard.pages.setCurrentIndex(i)
        if i == 0:
            wizard.wiz_meter._level = 0.55
        if i == 1:
            wizard.dl_bar.show()
            wizard.dl_bar.setValue(62)
            wizard.dl_label.setText(tr("wiz.model.downloading", pct=62))
        if i == 2:
            wizard.training_edit.setPlainText("Привет, это Parrotype — проверка связи.")
        wizard._sync_footer()
        _app.processEvents()
        shots.append((caption, _grab(wizard)))
    wizard._stop_monitor()
    wizard.deleteLater()

    pad = 30
    cell_w = (1600 - pad * 4) // 3
    scale = cell_w / shots[0][1].width
    font_c = _font(24)
    font_t = _font(34)
    cell_h = int(shots[0][1].height * scale)
    canvas = Image.new("RGBA", (1600, 140 + cell_h + 60), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((48, 28), "Parrotype — first-run wizard (real app render)", font=font_t, fill=TITLE)
    for i, (caption, img) in enumerate(shots):
        x = pad + i * (cell_w + pad)
        big = img.resize((cell_w, cell_h), Image.LANCZOS)
        canvas.alpha_composite(big, (x, 100))
        draw.text((x, 100 + cell_h + 10), caption, font=font_c, fill=CAPTION)
    return canvas


# -- tray menu -------------------------------------------------------------------


def render_menu() -> Image.Image:
    menu = QMenu()
    _hide_from_screen(menu)
    status = QAction("Готов · large-v3-turbo @ cuda (float16)")
    status.setEnabled(False)
    menu.addAction(status)
    menu.addSeparator()
    menu.addAction(QAction(tr("tray.copy_last"), menu))
    pause = QAction(tr("tray.pause"), menu)
    pause.setCheckable(True)
    pause.setChecked(True)
    menu.addAction(pause)
    menu.addSeparator()
    menu.addAction(QAction(tr("tray.settings"), menu))
    menu.addAction(QAction(tr("tray.history"), menu))
    menu.addSeparator()
    menu.addAction(QAction(tr("tray.quit"), menu))
    menu.resize(menu.sizeHint())
    img = _grab(menu)
    menu.deleteLater()

    scale = 2.4
    big = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    font_t = _font(34)
    font_c = _font(26)
    canvas = Image.new("RGBA", (1600, big.height + 170), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((48, 28), "Parrotype — tray context menu (QSS-styled, real render)", font=font_t, fill=TITLE)
    canvas.alpha_composite(big, ((1600 - big.width) // 2, 100))
    draw.text((48, 100 + big.height + 12), "Status line + copy last + pause (checked) + settings/history/quit", font=font_c, fill=CAPTION)
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, renderer in (
        ("pill-states.png", render_pill_states),
        ("settings-tabs.png", render_settings),
        ("wizard-steps.png", render_wizard),
        ("tray-menu.png", render_menu),
    ):
        image = renderer()
        image.convert("RGB").save(OUT / name)
        print(f"written {OUT / name}", file=sys.stderr)


if __name__ == "__main__":
    main()
