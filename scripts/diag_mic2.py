"""Decisive test v2: capture the Realtek Microphone Array via WASAPI,
trying channel counts and rates; shared and exclusive (raw) modes.

Run:  .venv\\Scripts\\python scripts\\diag_mic2.py
Speak continuously the whole time.
"""

from __future__ import annotations

import numpy as np
import sounddevice as sd

SECONDS = 4


def find_wasapi_array() -> int | None:
    hostapis = sd.query_hostapis()
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) <= 0:
            continue
        if "Array" not in dev["name"]:
            continue
        if "WASAPI" in hostapis[dev["hostapi"]]["name"]:
            return idx
    return None


def grab(idx: int, label: str, exclusive: bool) -> bool:
    dev = sd.query_devices(idx)
    rates = [int(dev["default_samplerate"]), 48000, 44100, 16000]
    chans = [dev["max_input_channels"], 2, 1, 4]
    tried = set()
    for rate in rates:
        for ch in chans:
            if ch < 1 or (rate, ch) in tried:
                continue
            tried.add((rate, ch))
            extra = {"extra_settings": sd.WasapiSettings(exclusive=True)} if exclusive else {}
            try:
                rec = sd.rec(SECONDS * rate, samplerate=rate, channels=ch,
                             dtype="float32", device=idx, **extra)
                sd.wait()
            except Exception:  # noqa: BLE001
                continue
            mono = rec[:, 0]
            rms = float(np.sqrt(np.mean(mono**2)))
            peak = float(np.max(np.abs(mono)))
            verdict = "СЛЫШИТ РЕЧЬ" if peak > 0.03 else ("шум/тихо" if peak > 1e-3 else "тишина")
            print(f"{label:<26} rate={rate} ch={ch}  rms={rms:.5f} peak={peak:.5f} -> {verdict}")
            return True
    print(f"{label:<26} не открылся ни один формат")
    return False


def main() -> None:
    idx = find_wasapi_array()
    if idx is None:
        print("WASAPI-эндпоинт массива не найден")
        return
    dev = sd.query_devices(idx)
    print(f"Устройство [{idx}] {dev['name']} (max_in={dev['max_input_channels']}, "
          f"default_rate={dev['default_samplerate']})")
    print("ГОВОРИ БЕЗ ПАУЗ ~10-15 секунд...\n")
    grab(idx, "WASAPI shared:", exclusive=False)
    grab(idx, "WASAPI exclusive (raw):", exclusive=True)


if __name__ == "__main__":
    main()
