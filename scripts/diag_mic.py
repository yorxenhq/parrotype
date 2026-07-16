"""Interactive mic diagnostic: records from every input device while you speak.

Run:  .venv\\Scripts\\python scripts\\diag_mic.py
Speak continuously ("raz-dva-tri...") the whole time it runs.
A device that hears speech shows PEAK well above its silent floor (>0.03).
"""

from __future__ import annotations

import sys

import numpy as np
import sounddevice as sd

SECONDS = 3
RATE = 16000


def main() -> None:
    print("ГОВОРИ БЕЗ ПАУЗ всё время теста (~15-20 сек): раз-два-три-четыре...\n")
    seen: set[str] = set()
    results = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) <= 0:
            continue
        name = dev["name"]
        if name in seen:  # same device via another host API
            continue
        seen.add(name)
        sys.stdout.write(f"[{idx:>2}] {name[:45]:<45} ... ")
        sys.stdout.flush()
        try:
            rec = sd.rec(SECONDS * RATE, samplerate=RATE, channels=1,
                         dtype="float32", device=idx)
            sd.wait()
            rms = float(np.sqrt(np.mean(rec**2)))
            peak = float(np.max(np.abs(rec)))
            verdict = "СЛЫШИТ РЕЧЬ" if peak > 0.03 else ("шум/тихо" if peak > 1e-3 else "тишина")
            print(f"rms={rms:.5f} peak={peak:.5f}  -> {verdict}")
            results.append((peak, idx, name))
        except Exception as exc:  # noqa: BLE001
            print(f"ERR {exc}")
    if results:
        best = max(results)
        print(f"\nЛучший кандидат: [{best[1]}] {best[2]} (peak={best[0]:.5f})")


if __name__ == "__main__":
    main()
