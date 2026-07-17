"""Render promo art (README hero, social preview) from the design kit.

Sources: design/kit/promo/readme-hero.html and social-preview.html — the
canonical Claude Design exports, each holding an EN and a RU variant as a
fixed-size block. This script extracts every variant into a standalone
page and screenshots it with headless Chrome at exact size.

Outputs:
  assets/promo/readme-hero-en.png   1280x400 @2x (README header)
  assets/promo/readme-hero-ru.png   1280x400 @2x
  assets/promo/social-preview-en.png 1280x640 @1x (OG convention)
  assets/promo/social-preview-ru.png 1280x640 @1x
  docs/site/og.png                  <- copy of social-preview-en.png

Run: python scripts/render_promo.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMO = ROOT / "design" / "kit" / "promo"
OUT = ROOT / "assets" / "promo"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

# (source file, element id, width, height, scale, output name)
JOBS = [
    ("readme-hero.html", "hero-en", 1280, 400, 2, "readme-hero-en.png"),
    ("readme-hero.html", "hero-ru", 1280, 400, 2, "readme-hero-ru.png"),
    ("social-preview.html", "og-en", 1280, 640, 1, "social-preview-en.png"),
    ("social-preview.html", "og-ru", 1280, 640, 1, "social-preview-ru.png"),
]


def chrome() -> str:
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    raise SystemExit("no headless-capable browser found")


def extract_block(html: str, element_id: str) -> str:
    """The variant block: from its opening div to the next caption/body end."""
    start = html.index(f'id="{element_id}"')
    start = html.rindex("<div", 0, start)
    next_cap = html.find('<div class="cap">', start)
    end = next_cap if next_cap != -1 else html.index("</body>")
    return html[start:end]


def build_standalone(src: Path, element_id: str, width: int, height: int) -> str:
    html = src.read_text(encoding="utf-8")
    style = re.search(r"<style>(.*?)</style>", html, re.DOTALL).group(1)
    block = extract_block(html, element_id)
    font_css = (PROMO / "space-grotesk.css").read_text(encoding="utf-8")
    # Inline the @font-face with an absolute file URL so the temp page
    # finds the woff2 regardless of where it lives.
    woff = (ROOT / "docs" / "site" / "fonts" / "space-grotesk.woff2").resolve()
    font_css = font_css.replace(
        "url(../../../docs/site/fonts/space-grotesk.woff2)",
        f"url('file:///{woff.as_posix()}')",
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>{font_css}</style>
<style>{style}
/* standalone reset: the block IS the page */
body{{margin:0;padding:0;background:#101014;display:block}}
.cap{{display:none}}
body>*{{position:relative!important;left:0!important;top:0!important;margin:0!important}}
</style></head><body>{block}</body></html>"""


def main() -> int:
    browser = chrome()
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="parrotype-promo-") as tmp:
        for src_name, element_id, width, height, scale, out_name in JOBS:
            page = Path(tmp) / f"{element_id}.html"
            page.write_text(
                build_standalone(PROMO / src_name, element_id, width, height),
                encoding="utf-8",
            )
            out = OUT / out_name
            cmd = [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--window-size={width},{height}",
                f"--force-device-scale-factor={scale}",
                f"--screenshot={out}",
                page.as_uri(),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if not out.exists():
                print(result.stderr[-800:])
                raise SystemExit(f"render failed: {out_name}")
            print("wrote", out.relative_to(ROOT), f"({width}x{height}@{scale}x)")
    shutil.copyfile(OUT / "social-preview-en.png", ROOT / "docs" / "site" / "og.png")
    print("wrote docs/site/og.png (= social-preview-en)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
