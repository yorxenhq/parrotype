"""Microphone capture via sounddevice: 16 kHz mono float32 frames.

The Recorder collects audio between start() and stop() and reports an
RMS level per block through an optional callback (used by the UI for
the live waveform). No UI dependencies here.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

LevelCallback = Callable[[float], None]

_NEVER_OPENED = object()   # Recorder._open_device sentinel


VIRTUAL_DEVICE_MARKERS = (
    "virtual", "steam streaming", "sound mapper", "voice changer",
    "cable", "vb-audio", "voicemeeter", "stereo mix",
)


def is_virtual_device(name: str) -> bool:
    """Heuristic: virtual/loopback endpoints that must not be a dictation mic."""
    lowered = name.lower()
    return any(marker in lowered for marker in VIRTUAL_DEVICE_MARKERS)


def list_input_devices(skip_virtual: bool = False) -> list[tuple[int, str]]:
    """(index, name) of all input-capable devices."""
    import sounddevice as sd

    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            if skip_virtual and is_virtual_device(dev["name"]):
                continue
            devices.append((idx, dev["name"]))
    return devices


def pick_input_device(preferred: int | None = None) -> int | None:
    """Resolve the capture device for dictation.

    Order: user's explicit choice (verified to still exist) -> the Windows
    default input if it is a real (non-virtual) device -> the first real
    input device. Returns None only when nothing can be resolved (which
    means "let the backend use its default").
    """
    import sounddevice as sd

    all_inputs = list_input_devices()
    valid_ids = {idx for idx, _ in all_inputs}
    if preferred is not None and preferred in valid_ids:
        return preferred

    real_inputs = [(i, n) for i, n in all_inputs if not is_virtual_device(n)]
    try:
        default_idx = sd.default.device[0]
    except Exception:
        default_idx = None
    if default_idx is not None and default_idx >= 0:
        default_name = next((n for i, n in all_inputs if i == default_idx), None)
        if default_name is not None and not is_virtual_device(default_name):
            return default_idx
        log.warning("System default input %r is virtual/unknown; skipping", default_name)
    if real_inputs:
        return real_inputs[0][0]
    return None


def probe_peak(device: int | None, seconds: float = 0.5, sample_rate: int = 16000) -> float:
    """Capture briefly and return the peak amplitude (0.0 on failure).

    Used by the startup self-check: a healthy microphone in a normal room
    never delivers exact digital silence.
    """
    import sounddevice as sd

    try:
        frames = int(seconds * sample_rate)
        data = sd.rec(
            frames, samplerate=sample_rate, channels=1, dtype="float32", device=device
        )
        sd.wait()
        return float(np.max(np.abs(data)))
    except Exception as exc:
        log.warning("Mic probe failed on device %s: %s", device, exc)
        return 0.0


class Recorder:
    """Push-to-talk style recorder: start() ... stop() -> np.float32 mono.

    WARM-STREAM DESIGN (the "first word was eaten" fix): creating a WASAPI
    input stream costs 100-300 ms — dictations lost their first syllable
    («тестирую» -> «стирую») because the user speaks the instant they press
    the hotkey. The stream is therefore opened ONCE and kept open-but-
    stopped between dictations; start() on a warm stream is milliseconds.
    A stopped stream does not capture and does not light the Windows
    microphone indicator — the privacy story is unchanged.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        device: int | None = None,
        on_level: LevelCallback | None = None,
        block_ms: int = 50,
    ):
        self.sample_rate = sample_rate
        self.device = device
        self.on_level = on_level
        self.blocksize = int(sample_rate * block_ms / 1000)
        self._stream = None
        self._open_device: object = _NEVER_OPENED
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if not self._recording:
            return                    # warm stream between dictations
        if status:
            log.debug("Audio stream status: %s", status)
        mono = indata[:, 0].copy()
        with self._lock:
            self._chunks.append(mono)
        if self.on_level is not None:
            rms = float(np.sqrt(np.mean(np.square(mono))))
            self.on_level(rms)

    def ensure_open(self) -> None:
        """Open (but do not start) the stream — the warm-up half of start().

        Called in the background at app startup so even the very first
        dictation begins capturing within milliseconds of the hotkey.
        """
        import sounddevice as sd

        if self._stream is not None and self._open_device == self.device:
            return
        self.close()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            device=self.device,
            latency="low",
            callback=self._callback,
        )
        self._open_device = self.device

    def start(self) -> None:
        if self._recording:
            return
        with self._lock:
            self._chunks = []
        try:
            self.ensure_open()
            assert self._stream is not None
            self._recording = True    # before start(): no callback frame lost
            self._stream.start()
        except Exception:
            self._recording = False
            self.close()              # stale/unplugged device: next try reopens
            raise

    def stop(self) -> np.ndarray:
        """Stop capturing and return the take; the stream stays warm."""
        if not self._recording:
            return np.zeros(0, dtype=np.float32)
        self._recording = False
        try:
            assert self._stream is not None
            self._stream.stop()
        except Exception as exc:
            log.warning("Stream stop failed (%s); closing", exc)
            self.close()
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            audio = np.concatenate(self._chunks)
            self._chunks = []
        return audio

    def cancel(self) -> None:
        """Stop and discard."""
        self.stop()

    def close(self) -> None:
        """Fully release the device (app quit / device switch)."""
        self._recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._open_device = _NEVER_OPENED
