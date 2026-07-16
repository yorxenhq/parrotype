"""Render the website screenshot set (docs/site/img/) from the real app UI.

Same rules as render_ui_previews.py: QWidget.grab/render only, offscreen
(WA_DontShowOnScreen) — no screen capture, no input injection. EN locale,
neutral demo data, no personal information. Widgets are rendered through a
scaled QPainter so the shots land at ~1100 px wide and stay crisp.

Run: python scripts/render_site_screens.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault(
    "PARROTYPE_DATA_DIR",
    str(Path(os.environ.get("TEMP", ".")) / "parrotype_site_shots"),
)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtCore import QBuffer, QPoint, Qt  # noqa: E402
from PySide6.QtGui import QAction, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from core import Config, History  # noqa: E402
from core.history import HistoryEntry  # noqa: E402
from shells.tray import theme  # noqa: E402
from shells.tray.i18n import set_language, tr  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "site" / "img"
BG = (16, 16, 20)
CAPTION = (154, 154, 166)
MAX_W = 1100
SCALE = 1.45          # 760-wide dialog -> ~1100 px

_app = QApplication(sys.argv)
theme.load_fonts()
_app.setStyleSheet(theme.app_qss())
set_language("en")


def _hide(widget) -> None:  # noqa: ANN001
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)


def _to_pil(pixmap) -> Image.Image:  # noqa: ANN001
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    pixmap.save(buffer, "PNG")
    import io

    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")


def _grab_scaled(widget, scale: float = SCALE) -> Image.Image:  # noqa: ANN001
    """widget.render through a scaled painter — crisp text at ~1.5x."""
    w = int(widget.width() * scale)
    h = int(widget.height() * scale)
    pixmap = QPixmap(w, h)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.scale(scale, scale)
    widget.render(painter, QPoint(0, 0))
    painter.end()
    return _to_pil(pixmap)


def _save(img: Image.Image, name: str) -> None:
    if img.width > MAX_W:
        img = img.resize(
            (MAX_W, int(img.height * MAX_W / img.width)), Image.LANCZOS
        )
    img.convert("RGB").save(OUT / name, optimize=True)
    print(f"written {OUT / name}", file=sys.stderr)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _demo_history() -> History:
    history = History(limit=50)
    now = time.time()
    seed = [
        # oldest first — History keeps append order, shows newest first
        ("Pick up the parcel from the locker on the way home", now - 3 * 86400, 2.0),
        ("The quarterly report needs one more pass before Friday", now - 86400, 75.0),
        ("Remind me to check the deploy logs after lunch", now - 7200, 3.0),
        ("Draft a short status update for the team and post it in the channel", now - 300, 6.0),
    ]
    for text, ts, secs in seed:
        history.add(text, secs)
        history._entries[-1].timestamp = ts   # neutral demo timestamps
    return history


def _make_dialog():  # noqa: ANN001
    from shells.tray.settings import SettingsDialog

    from shells.tray.modelpicker import machine_options

    config = Config()
    config.replacements = {"clod": "Claude", "cloud flare": "Cloudflare"}
    config.recognition_context = "Claude Code, Cloudflare, Kubernetes"
    # Select the recommended model so the shot is self-consistent.
    options, _note = machine_options()
    config.model_size = next(
        (o.name for o in options if o.recommended), options[0].name
    )
    dialog = SettingsDialog(config, _demo_history())
    _hide(dialog)
    dialog.resize(760, 560)
    return dialog


def render_settings_tabs() -> None:
    dialog = _make_dialog()
    dialog.level_meter._level = 0.55                 # live level, like mid-speech
    # Real measured numbers (scripts/benchmark.py, README): 13 s phrase in
    # ~0.8 s on a laptop GPU with large-v3-turbo, ~1.4 s on CPU with small.
    if dialog.config.model_size == "large-v3-turbo":
        latency = tr("set.latency_result", model="large-v3-turbo", dev="GPU", lat="0.8", dur="13")
    else:
        latency = tr("set.latency_result", model="small", dev="CPU", lat="1.4", dur="13")
    dialog.latency_label.setText(latency + tr("set.latency_fast"))
    tabs = {
        0: "settings-general.png",
        1: "settings-model.png",
        2: "settings-dictionary.png",
        3: "settings-history.png",
    }
    for row, name in tabs.items():
        dialog.sidebar.setCurrentRow(row)
        _app.processEvents()
        _save(_grab_scaled(dialog), name)

    # Crop for Troubleshooting: microphone combo + live level meter.
    dialog.sidebar.setCurrentRow(0)
    _app.processEvents()
    full = _grab_scaled(dialog)
    top = dialog.mic_combo.mapTo(dialog, QPoint(0, 0)).y()
    # The level meter is 8 px tall; take the whole row incl. its label.
    bottom = dialog.level_meter.mapTo(dialog, QPoint(0, dialog.level_meter.height())).y() + 16
    x0 = 160                                          # start after the sidebar
    pad = 14
    crop = full.crop((
        int((x0 + 2) * SCALE),
        int(max(0, top - pad) * SCALE),
        full.width,
        int(min(dialog.height(), bottom + pad) * SCALE),
    ))
    _save(crop, "settings-mic-level.png")
    dialog.deleteLater()


def render_wizard_steps() -> None:
    from shells.tray.modelpicker import machine_options
    from shells.tray.wizard import FirstRunWizard

    config = Config()
    options, _note = machine_options()
    config.model_size = next(
        (o.name for o in options if o.recommended), options[0].name
    )
    wizard = FirstRunWizard(config)
    _hide(wizard)
    steps = {0: "wizard-1-mic.png", 1: "wizard-2-model.png", 2: "wizard-3-hotkey.png"}
    for i, name in steps.items():
        wizard.pages.setCurrentIndex(i)
        if i == 0:
            wizard.wiz_meter._level = 0.55
            wizard.mic_status.setText(tr("wiz.mic.ok"))
        if i == 1:
            wizard.dl_bar.show()
            wizard.dl_bar.setValue(62)
            wizard.dl_label.setText(tr("wiz.model.downloading", pct=62))
        if i == 2:
            wizard.training_edit.setPlainText(
                "Hello, this is Parrotype — testing the first dictation."
            )
        wizard._sync_footer()
        _app.processEvents()
        _save(_grab_scaled(wizard), name)
    wizard._stop_monitor()
    wizard.deleteLater()


def render_pill_states() -> None:
    from shells.tray.overlay import OverlayPill

    demo_levels = [0.28, 0.62, 0.95, 0.7, 0.4, 0.55, 0.8, 0.35,
                   0.6, 0.9, 0.5, 0.3, 0.66, 0.45]
    states = [
        ("listening", "Listening — live waveform, elapsed time"),
        ("transcribing", "Transcribing"),
        ("status", "First run — model download"),
        ("inserted", "Inserted"),
        ("error", "Error — stays until you act"),
    ]
    shots = []
    for key, caption in states:
        pill = OverlayPill()
        _hide(pill)
        if key == "listening":
            pill.show_listening("en", toggle_mode=False)
            pill._heights = demo_levels
            pill._elapsed_ms = 7000
        elif key == "transcribing":
            pill.show_transcribing()
        elif key == "status":
            pill.show_status(tr("pill.downloading_model", pct=62))
        elif key == "inserted":
            pill.show_inserted("Draft a short status update for the team")
        elif key == "error":
            pill.show_error(tr("pill.insert_failed"))
        pill._anim.stop()
        pill._tick_timer.stop()
        pill._anim_t = 1.0
        shots.append((caption, _to_pil(pill.grab())))
        pill.deleteLater()

    scale = 1.9
    font_c = _font(20)
    rows = [
        (cap, img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS))
        for cap, img in shots
    ]
    row_h = max(img.height for _, img in rows) + 44
    canvas = Image.new("RGBA", (MAX_W, 36 + row_h * len(rows)), BG)
    draw = ImageDraw.Draw(canvas)
    y = 36
    for caption, img in rows:
        canvas.alpha_composite(img, ((MAX_W - img.width) // 2, y))
        draw.text(
            ((MAX_W - draw.textlength(caption, font=font_c)) // 2, y + img.height + 8),
            caption, font=font_c, fill=CAPTION,
        )
        y += row_h
    _save(canvas, "pill-states.png")


def render_tray_menu() -> None:
    menu = QMenu()
    _hide(menu)
    status = QAction("Ready · large-v3-turbo · GPU")
    status.setEnabled(False)
    menu.addAction(status)
    menu.addSeparator()
    menu.addAction(QAction(tr("tray.copy_last"), menu))
    pause = QAction(tr("tray.pause"), menu)
    pause.setCheckable(True)
    menu.addAction(pause)
    menu.addSeparator()
    menu.addAction(QAction(tr("tray.settings"), menu))
    menu.addAction(QAction(tr("tray.history"), menu))
    menu.addSeparator()
    menu.addAction(QAction(tr("tray.quit"), menu))
    menu.resize(menu.sizeHint())
    img = _grab_scaled(menu, scale=2.0)
    menu.deleteLater()
    pad = 28
    canvas = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), BG)
    canvas.alpha_composite(img, (pad, pad))
    _save(canvas, "tray-menu.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    render_pill_states()
    render_wizard_steps()
    render_settings_tabs()
    render_tray_menu()


if __name__ == "__main__":
    main()
