"""A/B harness for the polish layer: real garbled dictations, before/after.

Run: python scripts/ab_polish.py
Prints raw -> polished, latency, and the guard verdict for each case.
The cases mirror the owner's actual dictation style: Russian speech with
fillers, self-corrections and English tech terms mixed in.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.polish import PolishEngine  # noqa: E402

CASES = [
    # (raw, dictionary_terms)
    ("эээ ну короче нужно поправить настройки микрофона а то он опять эээ фонит", []),
    ("запусти тесты нет подожди сначала пересобери проект а потом запусти тесты", []),
    ("добавь в клауд код поддержку новой модели ну и задеплой на клаудфлер",
     ["Claude Code", "Cloudflare"]),
    ("встречу переносим на три нет давай на четыре часа в четверг", []),
    ("um so we need to uh push the release by friday no wait by thursday evening", []),
    ("напиши антону что отчёт обновится завтра утром ну то есть цифры подтянутся сами", []),
    ("раз два раз два проверка связи как меня слышно приём", []),
    ("сделай рефакторинг воркера эээ там где айписи протокол ну чтобы читалось проще", []),
]


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else None
    engine = PolishEngine(model) if model else PolishEngine()
    print(f"Model: {engine.model} — downloading if missing...")
    engine.ensure_model()
    print("Loading model (CPU)...")
    load_s = engine.load()
    print(f"Loaded in {load_s:.1f}s\n")

    total, changed, fell_back = 0, 0, 0
    for raw, terms in CASES:
        result = engine.polish(raw, dictionary_terms=terms, deadline_s=20.0)
        total += 1
        changed += result.changed
        fell_back += result.fell_back
        status = "FELL BACK (" + result.reason + ")" if result.fell_back else (
            "changed" if result.changed else "unchanged"
        )
        print(f"[{result.latency_seconds:5.2f}s] {status}")
        print(f"  RAW: {raw}")
        print(f"  OUT: {result.text}")
        print()
    print(f"=== {total} cases: {changed} changed, {fell_back} fell back ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
