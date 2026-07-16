# Parrotype design kit

Self-contained HTML preview cards for design iteration (Claude Design /
DesignSync-style). Each file in `kit/` is one card: first line is the
`<!-- @dsCard group="..." -->` marker, everything inline, no external
dependencies, page background `#101014`.

## Cards

| File | Group | Shows |
|---|---|---|
| `kit/tokens.html` | Foundations | Palette, typography, radii, motion + sound rules |
| `kit/logo.html` | Brand | Canonical mark (assets/logo.svg), wordmark, slogans, 32/16px tray variants |
| `kit/overlay.html` | Components | Status pill, all 4 states (listening PTT/toggle, transcribing, inserted, error) |
| `kit/tray.html` | Components | Tray icon states (idle/rec/paused) at 16/32px + context menu |
| `kit/settings.html` | Components | Settings window, sidebar + "Общее" tab, QSS-accurate |
| `kit/wizard.html` | Components | First-run wizard concept, 3 steps — **CONCEPT, not in code yet** |

## Rules

- **Canon of tokens = spec §3.5** (mirrored in `shells/tray/theme.py`).
  The kit is a showcase, not a source of truth: when tokens change, the
  spec and `theme.py` change first, the kit follows.
- Previews must not lie about the current state of the app. Known
  deliberate embellishments are annotated inside the cards themselves
  (tray menu is native Qt in the app, not token-styled; settings
  titlebar/checkbox/combo chrome is native; wizard is a concept).
- The mark is rendered from `assets/logo.svg` at runtime — the kit
  embeds the same SVG verbatim, never a redrawn copy.

## Sync

Upload the `kit/*.html` files as cards into the design tool, iterate
there, then bring approved changes back: spec §3.5 -> `theme.py` /
`overlay.py` / `settings.py` -> re-render the kit to match. One
direction at a time; the repo always reflects what shipped.
