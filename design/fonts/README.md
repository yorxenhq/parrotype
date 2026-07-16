# Fonts (typography options)

Variable TTFs downloaded from the official Google Fonts repository for
the typography comparison (`design/preview/typography-options.png`):

- `Manrope[wght].ttf` — SIL Open Font License 1.1 (supports Cyrillic)
- `SpaceGrotesk[wght].ttf` — SIL Open Font License 1.1 (**no Cyrillic**:
  RU headings would fall back to Segoe — visible in variant C)

Nothing is applied in the app yet. When the owner picks a variant, the
chosen font gets bundled (OFL permits redistribution; include the OFL
license text alongside) and wired into theme.py + app QSS.
