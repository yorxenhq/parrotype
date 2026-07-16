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
        self._warmed_key: tuple[str, str, str] | None = None

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
        # Cache hit -> fully offline load (no network round-trips at all;
        # part of the "nothing leaves this machine" guarantee).
        offline = self.is_model_cached()
        try:
            self._model = WhisperModel(
                self.config.model_size, device=device, compute_type=compute,
                local_files_only=offline,
            )
        except (RuntimeError, ValueError) as exc:
            if device == "cuda":
                log.warning("CUDA load failed (%s); falling back to CPU int8", exc)
                device, compute = "cpu", "int8"
                key = (self.config.model_size, device, compute)
                self._model = WhisperModel(
                    self.config.model_size, device=device, compute_type=compute,
                    local_files_only=offline,
                )
            else:
                raise
        self._model_key = key
        log.info("Model ready in %.1fs", time.perf_counter() - t0)

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    def is_model_cached(self) -> bool:
        """True when the current model's weights are already on disk."""
        from faster_whisper.utils import download_model

        try:
            download_model(self.config.model_size, local_files_only=True)
            return True
        except Exception:
            return False

    def ensure_model(self, progress_cb=None) -> None:
        """Download the model if missing, reporting percent via progress_cb(int).

        Percent tracks the byte-level tqdm bars of the snapshot download
        (the multi-GB weights file dominates, so it reads naturally).
        """
        if self.is_model_cached():
            return
        from faster_whisper.utils import _MODELS
        from huggingface_hub import snapshot_download
        from tqdm import tqdm as _tqdm

        repo_id = _MODELS.get(self.config.model_size, self.config.model_size)

        class _ProgressTqdm(_tqdm):
            def update(self, n=1):  # noqa: ANN001
                result = super().update(n)
                try:
                    if (
                        progress_cb is not None
                        and self.total
                        and self.total > 1_000_000   # byte bars only, not file counters
                    ):
                        progress_cb(min(100, int(self.n * 100 / self.total)))
                except Exception:
                    pass
                return result

        log.info("Downloading model %s (%s)", self.config.model_size, repo_id)
        snapshot_download(repo_id, tqdm_class=_ProgressTqdm)
        if progress_cb is not None:
            progress_cb(100)

    def unload_model(self) -> None:
        self._model = None
        self._model_key = None

    def warm_up(self) -> float:
        """Throwaway decode to warm the inference kernels; returns seconds.

        The first CUDA transcription after load_model pays a large one-time
        cost (kernel compilation/caching); running it on 0.5s of noise in
        the background makes the first real dictation respond instantly.
        VAD is disabled so the encoder+decoder actually execute.
        """
        self.load_model()
        assert self._model is not None
        if self._warmed_key == self._model_key:
            return 0.0
        noise = (np.random.default_rng(0).standard_normal(
            int(0.5 * self.config.sample_rate)
        ) * 0.02).astype(np.float32)
        t0 = time.perf_counter()
        segments, _ = self._model.transcribe(
            noise, language="en", vad_filter=False, beam_size=1,
            temperature=0, condition_on_previous_text=False,
        )
        for _segment in segments:
            pass
        self._warmed_key = self._model_key
        elapsed = time.perf_counter() - t0
        log.info("Engine warm-up finished in %.2fs", elapsed)
        return elapsed

    # -- transcription ---------------------------------------------------

    def _trim_silence(self, audio: "np.ndarray") -> "np.ndarray":
        """Trim leading/trailing quiet with a numpy energy gate.

        Replaces faster-whisper's Silero VAD: its onnxruntime session
        intermittently access-violated on CPU in the packaged build (~15%).
        A frame-RMS gate cuts the quiet tail/head — which is what actually
        mattered (a breathing/mumble tail decoded into hallucinated words)
        — deterministically, with no native VAD dependency.
        """
        sr = self.config.sample_rate
        frame = max(1, int(0.03 * sr))                 # 30 ms frames
        pad = int(0.2 * sr)                            # keep 200 ms around speech
        n = len(audio)
        if n < frame * 2:
            return audio
        trimmed = n - (n % frame)
        frames = audio[:trimmed].reshape(-1, frame)
        rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
        peak = float(rms.max())
        gate = max(0.01, 0.08 * peak)                  # relative + absolute floor
        speech = np.where(rms > gate)[0]
        if speech.size == 0:
            return audio                               # all quiet: let whisper decide
        start = max(0, speech[0] * frame - pad)
        end = min(n, (speech[-1] + 1) * frame + pad)
        return np.ascontiguousarray(audio[start:end], dtype=np.float32)

    def transcribe(self, audio: AudioInput) -> TranscriptionResult:
        """Transcribe a WAV file path or a float32 mono 16 kHz numpy array."""
        self.load_model()
        assert self._model is not None

        if isinstance(audio, np.ndarray):
            audio_data: AudioInput = self._trim_silence(
                np.ascontiguousarray(audio, dtype=np.float32)
            )
            audio_seconds = len(audio_data) / self.config.sample_rate
        else:
            audio_data = str(audio)
            audio_seconds = 0.0  # filled from model info below

        language = None if self.config.language == "auto" else self.config.language

        t0 = time.perf_counter()
        segments_iter, info = self._model.transcribe(
            audio_data,
            language=language,
            # No onnxruntime VAD: the quiet tail is already trimmed in numpy
            # (_trim_silence) before this call. The Silero VAD crashed the
            # packaged CPU build intermittently; the trim + the decode guards
            # below cover the same hallucination-on-silence case.
            vad_filter=False,
            # Greedy single-pass decode. beam search + the temperature
            # fallback cascade intermittently access-violated ctranslate2's
            # CPU int8 kernels in the packaged build (~15%); the warm-up,
            # which uses exactly beam_size=1/temperature=0, never crashes.
            # Quality on dictation-length audio is effectively identical.
            beam_size=1,
            condition_on_previous_text=False,     # no cross-segment drift
            temperature=0.0,
            no_speech_threshold=0.6,              # drop segments the model deems non-speech
            log_prob_threshold=-1.0,              # reject low-confidence decodes
            compression_ratio_threshold=2.4,      # reject repetitive gibberish
            initial_prompt=self.initial_prompt(),
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

    def initial_prompt(self) -> str | None:
        """Recognition seed: unique dictionary targets + user context.

        The right-hand sides of the replacement dictionary are exactly the
        terms the user dictates (product names, tech vocabulary), so they
        bias Whisper toward the correct spelling. The free-form recognition
        context from settings is appended. Empty -> None (unchanged behavior).
        """
        seen: dict[str, None] = {}
        for value in self.config.replacements.values():
            term = value.strip()
            if term:
                seen.setdefault(term)
        parts = []
        if seen:
            parts.append(", ".join(seen) + ".")
        context = (self.config.recognition_context or "").strip()
        if context:
            parts.append(context)
        return " ".join(parts) or None

    def reload_postfilter(self) -> None:
        """Re-read replacement dictionary from config (after settings change)."""
        self.postfilter = PostFilter(self.config.replacements)
