"""Quiet start/stop ticks, generated in memory (no asset files, no deps)."""

from __future__ import annotations

import io
import logging
import struct
import sys
import wave

log = logging.getLogger(__name__)

_SAMPLE_RATE = 22050


def _tone(freq: float, ms: int, volume: float = 0.18) -> bytes:
    """Short sine tick with fade-in/out envelope, as WAV bytes."""
    import math

    n = int(_SAMPLE_RATE * ms / 1000)
    frames = bytearray()
    for i in range(n):
        env = min(1.0, i / (n * 0.15), (n - i) / (n * 0.4))
        sample = volume * env * math.sin(2 * math.pi * freq * i / _SAMPLE_RATE)
        frames += struct.pack("<h", int(sample * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_SAMPLE_RATE)
        wav.writeframes(bytes(frames))
    return buf.getvalue()


_START_TICK = _tone(1175, 45)
_STOP_TICK = _tone(880, 45)


def _play(data: bytes) -> None:
    if sys.platform != "win32":
        return
    import winsound

    try:
        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
    except RuntimeError as exc:
        log.debug("Tick playback failed: %s", exc)


def play_start() -> None:
    _play(_START_TICK)


def play_stop() -> None:
    _play(_STOP_TICK)
