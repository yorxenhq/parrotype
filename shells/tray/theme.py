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

# Geometry
PILL_HEIGHT = 44
CARD_RADIUS = 12

# Motion
ANIM_MS = 180                # 150-200ms ease-out, no bounce

# Behaviour
LONG_RECORDING_S = 90        # timer switches to accent as a reminder
INSERTED_FLASH_MS = 800
INSERTED_FADE_MS = 400
