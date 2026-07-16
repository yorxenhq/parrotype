"""Design tokens for the Parrotype UI (dark-first 'quiet tool' style)."""

from __future__ import annotations

# Colors (spec-defined mini design system; deliberately brandless)
BG_OVERLAY = "#17171C"       # overlay pill background
BG_OVERLAY_ALPHA = 0xE0      # ~88% opacity
SURFACE = "#1E1E24"
TEXT = "#ECECF1"
MUTED = "#9A9AA6"
LINE = "#2E2E36"
ACCENT = "#4FD1B0"           # mint — "ready / active"
REC = "#FF5C5C"              # recording dot only

# Typography
FONT_UI = "Segoe UI Variable"
FONT_UI_FALLBACK = "Segoe UI"
FONT_MONO = "Cascadia Mono"
# Headings/wordmark/kickers — owner-approved variant C. Space Grotesk has
# no Cyrillic: RU headings intentionally fall back to Segoe (seen and
# accepted on the comparison collage).
FONT_HEADING = "Space Grotesk"
FONT_HEADING_CHAIN = f'"{FONT_HEADING}", "{FONT_UI}", "{FONT_UI_FALLBACK}"'


def load_fonts() -> None:
    """Register bundled fonts (assets/fonts) — call once after QApplication."""
    from pathlib import Path

    from PySide6.QtGui import QFontDatabase

    fonts_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    if not fonts_dir.is_dir():
        return
    for ttf in fonts_dir.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(ttf))

# Geometry
PILL_HEIGHT = 44
CARD_RADIUS = 12

# Motion
ANIM_MS = 180                # 150-200ms ease-out, no bounce

# Behaviour
LONG_RECORDING_S = 90        # timer switches to accent as a reminder
INSERTED_FLASH_MS = 800
INSERTED_FADE_MS = 400


def app_qss() -> str:
    """Application-wide dark stylesheet: menus, inputs, scrollbars, dialogs.

    Brings every native-ish Qt surface up to the design-kit look.
    """
    return f"""
    QDialog, QMessageBox {{ background: {SURFACE}; color: {TEXT}; }}
    QWidget {{ color: {TEXT}; font-family: "{FONT_UI}", "{FONT_UI_FALLBACK}"; font-size: 13px; }}
    QLabel#muted {{ color: {MUTED}; }}

    /* menus (tray context menu, combo popups) */
    QMenu {{
        background: {SURFACE}; color: {TEXT};
        border: 1px solid {LINE}; border-radius: 8px; padding: 6px;
    }}
    QMenu::item {{ padding: 8px 14px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {LINE}; }}
    QMenu::item:disabled {{ color: {MUTED}; }}
    QMenu::separator {{ height: 1px; background: {LINE}; margin: 5px 8px; }}
    QMenu::indicator {{ width: 14px; height: 14px; }}

    /* inputs */
    QLineEdit, QComboBox, QPlainTextEdit, QSpinBox {{
        background: {BG_OVERLAY}; border: 1px solid {LINE};
        border-radius: 6px; padding: 6px 8px; selection-background-color: {LINE};
    }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{
        image: none; width: 8px; height: 8px;
        border-left: 4px solid transparent; border-right: 4px solid transparent;
        border-top: 5px solid {MUTED}; margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE};
        border-radius: 6px; padding: 4px; selection-background-color: {LINE};
        outline: none;
    }}

    /* buttons */
    QPushButton {{
        background: {LINE}; border: none; border-radius: 6px; padding: 8px 16px;
    }}
    QPushButton:hover {{ background: #3A3A44; }}
    QPushButton:pressed {{ background: #26262E; }}
    QPushButton:disabled {{ color: {MUTED}; }}
    QPushButton#accent {{ background: {ACCENT}; color: #101014; font-weight: 600; }}
    QPushButton#accent:hover {{ background: #63DBBD; }}
    QPushButton#accent:disabled {{ background: {LINE}; color: {MUTED}; font-weight: 400; }}

    /* checkboxes */
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border: 1px solid {LINE};
        border-radius: 4px; background: {BG_OVERLAY};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT}; border-color: {ACCENT};
        image: url(none);
    }}
    QCheckBox::indicator:hover {{ border-color: {MUTED}; }}

    /* tables / lists */
    QTableWidget, QListWidget {{
        background: {BG_OVERLAY}; border: 1px solid {LINE};
        border-radius: 6px; padding: 4px; outline: none;
    }}
    QTableWidget::item, QListWidget::item {{ padding: 4px; border-radius: 4px; }}
    QTableWidget::item:selected, QListWidget::item:selected {{
        background: {LINE}; color: {TEXT};
    }}
    QHeaderView::section {{
        background: #191920; color: {MUTED}; border: none;
        border-bottom: 1px solid {LINE}; padding: 6px;
    }}
    QTableCornerButton::section {{ background: #191920; border: none; }}

    /* scrollbars */
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{
        background: {LINE}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: #3A3A44; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{
        background: {LINE}; border-radius: 4px; min-width: 24px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* progress bars */
    QProgressBar {{
        background: {LINE}; border: none; border-radius: 3px;
        height: 6px; text-align: center; color: transparent;
    }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

    QToolTip {{
        background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE};
        padding: 5px 8px; border-radius: 5px;
    }}

    /* model picker cards (wizard step 2 + settings "Model" page) */
    QFrame#modelcard {{
        background: {BG_OVERLAY}; border: 1px solid {LINE}; border-radius: 10px;
    }}
    QFrame#modelcard:hover {{ border-color: #4A4A56; }}
    QFrame#modelcard[selected="true"] {{ border-color: {ACCENT}; }}
    QLabel#modelname {{
        font-family: {FONT_HEADING_CHAIN}; font-size: 14px; font-weight: 600;
    }}
    QLabel#recchip {{
        background: rgba(79, 209, 176, 0.16); color: {ACCENT};
        border-radius: 8px; padding: 1px 8px; font-size: 11px;
    }}
    QLabel#modelmeta {{ color: {MUTED}; font-size: 11px; }}

    /* headings: Space Grotesk (owner-approved variant C); body stays Segoe */
    QLabel#steptitle {{ font-family: {FONT_HEADING_CHAIN}; font-size: 18px; font-weight: 700; }}
    QLabel#stepno {{ font-family: {FONT_HEADING_CHAIN}; }}
    QLabel#wordmark {{ font-family: {FONT_HEADING_CHAIN}; font-size: 26px; font-weight: 700; }}
    """
