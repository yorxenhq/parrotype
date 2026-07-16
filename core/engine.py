"""Speech engine: faster-whisper transcription with silero VAD and post-filtering.

Designed as a speech-I/O engine. v1 implements speech-to-text only;
the interface deliberately leaves room for a future text-to-speech
counterpart (e.g. ``speak(text)``) without breaking callers.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Union

import numpy as np

from core.config import Config
from core.postfilter import PostFilter

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

log = logging.getLogger(__name__)

AudioInput = Union[str, Path, np.ndarray]


def _register_cuda_dlls() -> None:
    """Make pip-installed NVIDIA runtime DLLs (cuBLAS/cuDNN) loadable on Windows.

    ctranslate2 loads these lazily at model init; the pip wheels put them in
    site-packages/nvidia/*/bin which is not on the DLL search path by default.
    """
    if sys.platform != "win32":
        return
    for base in map(Path, sys.path):
        nvidia = base / "nvidia"
        if not nvidia.is_dir():
            continue
        for sub in nvidia.iterdir():
            bin_dir = sub / "bin"
            if bin_dir.is_dir():
                try:
                    os.add_dll_directory(str(bin_dir))
                except OSError as exc:
                    log.debug("add_dll_directory(%s) failed: %s", bin_dir, exc)
                # ctranslate2 resolves cuBLAS/cuDNN with a plain LoadLibrary,
                # which ignores add_dll_directory dirs — PATH is also needed.
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


_register_cuda_dlls()


@dataclass
class TranscriptionResult:
    text: str                    # final text (post-filter applied)
    raw_text: str                # text as produced by the model
    language: str                # detected/forced language code
    audio_seconds: float         # duration of the input audio
    latency_seconds: float       # wall-clock time spent transcribing
    segments: list[str] = field(default_factory=list)


class Engine:
    """Speech-to-text engine. Thread-safe for sequential use; model loads lazily.

    Reserved for future versions (do not implement in v1):
        speak(text) -> audio   # reverse direction, TTS backend TBD
    """

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.postfilter = PostFilter(self.config.replacements)
        self._model: "WhisperModel | None" = None
        self._model_key: tuple[str, str, str] | None = None

    # -- model management ----------------------------------------------

    def load_model(self) -> None:
        """Load (or reload) the whisper model according to current config."""
        from faster_whisper import WhisperModel

        device, compute = self.config.resolve_device()
        key = (self.config.model_size, device, compute)
        if self._model is not None and key == self._model_key:
            return
        log.info("Loading model %s on %s (%s)", *key)
        t0 = time.perf_counter()
        try:
            self._model = WhisperModel(
                self.config.model_size, device=device, compute_type=compute
            )
        except (RuntimeError, ValueError) as exc:
            if device == "cuda":
                log.warning("CUDA load failed (%s); falling back to CPU int8", exc)
                device, compute = "cpu", "int8"
                key = (self.config.model_size, device, compute)
                self._model = WhisperModel(
                    self.config.model_size, device=device, compute_type=compute
                )
            else:
                raise
        self._model_key = key
        log.info("Model ready in %.1fs", time.perf_counter() - t0)

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    def unload_model(self) -> None:
        self._model = None
        self._model_key = None

    # -- transcription ---------------------------------------------------

    def transcribe(self, audio: AudioInput) -> TranscriptionResult:
        """Transcribe a WAV file path or a float32 mono 16 kHz numpy array."""
        self.load_model()
        assert self._model is not None

        if isinstance(audio, np.ndarray):
            audio_data: AudioInput = np.ascontiguousarray(audio, dtype=np.float32)
            audio_seconds = len(audio_data) / self.config.sample_rate
        else:
            audio_data = str(audio)
            audio_seconds = 0.0  # filled from model info below

        language = None if self.config.language == "auto" else self.config.language

        t0 = time.perf_counter()
        segments_iter, info = self._model.transcribe(
            audio_data,
            language=language,
            vad_filter=True,                      # silero VAD (bundled with faster-whisper)
            vad_parameters={"min_silence_duration_ms": 300},
            beam_size=5,
            condition_on_previous_text=False,     # dictation: avoid cross-utterance drift
        )
        segment_texts = [seg.text.strip() for seg in segments_iter]
        latency = time.perf_counter() - t0

        raw_text = " ".join(t for t in segment_texts if t).strip()
        text = self.postfilter.apply(raw_text)
        if not audio_seconds:
            audio_seconds = float(info.duration or 0.0)

        return TranscriptionResult(
            text=text,
            raw_text=raw_text,
            language=info.language,
            audio_seconds=audio_seconds,
            latency_seconds=latency,
            segments=segment_texts,
        )

    def reload_postfilter(self) -> None:
        """Re-read replacement dictionary from config (after settings change)."""
        self.postfilter = PostFilter(self.config.replacements)
