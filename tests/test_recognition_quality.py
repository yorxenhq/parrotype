"""Anti-hallucination and initial-prompt tests (tiny model, CPU).

Covers the quality iteration: a quiet noise tail after speech must not be
decoded into words, and the recognition seed (dictionary terms + user
context) must not break transcription.
"""

import wave
from pathlib import Path

import numpy as np
import pytest

from core import Config, Engine

DATA = Path(__file__).parent / "data"
WAV = DATA / "test_en.wav"
WAV_TERMS = DATA / "test_en_terms.wav"


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PARROTYPE_DATA_DIR", str(tmp_path))


def _make_engine(**cfg_overrides) -> Engine:
    cfg = Config(model_size="tiny", device="cpu", compute_type="int8", language="en")
    for key, value in cfg_overrides.items():
        setattr(cfg, key, value)
    return Engine(cfg)


def _load_wav_f32(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        assert wav.getframerate() == 16000 and wav.getnchannels() == 1
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0


# -- initial prompt construction (pure, fast) --------------------------------


def test_initial_prompt_empty_config_is_none():
    engine = _make_engine()
    assert engine.initial_prompt() is None


def test_initial_prompt_from_dictionary_targets():
    engine = _make_engine(
        replacements={"клод": "Claude", "кф": "Cloudflare", "клауд": "Claude"}
    )
    prompt = engine.initial_prompt()
    assert prompt == "Claude, Cloudflare."          # unique, order-stable


def test_initial_prompt_with_context():
    engine = _make_engine(
        replacements={"кф": "Cloudflare"},
        recognition_context="Dictation about container orchestration.",
    )
    prompt = engine.initial_prompt()
    assert prompt is not None
    assert "Cloudflare." in prompt
    assert prompt.endswith("Dictation about container orchestration.")


def test_initial_prompt_context_only():
    engine = _make_engine(recognition_context="  Solar panel installation.  ")
    assert engine.initial_prompt() == "Solar panel installation."


# -- anti-hallucination: quiet noise tail ------------------------------------


@pytest.mark.skipif(not WAV.exists(), reason="test audio not generated")
def test_quiet_noise_tail_does_not_become_words():
    """Speech + 2s of quiet noise: the tail must not turn into words."""
    engine = _make_engine()
    speech = _load_wav_f32(WAV)

    rng = np.random.default_rng(42)
    noise = (rng.standard_normal(2 * 16000) * 0.01).astype(np.float32)  # quiet hiss
    padded = np.concatenate([speech, noise])

    base = engine.transcribe(speech)
    tail = engine.transcribe(padded)

    base_words = base.raw_text.split()
    tail_words = tail.raw_text.split()
    # The noise tail must not add words (tiny jitter in the shared part allowed).
    assert len(tail_words) <= len(base_words) + 2, (
        f"noise tail hallucinated words:\n base: {base.raw_text}\n tail: {tail.raw_text}"
    )
    for keyword in ("settings", "latency", "offline"):
        assert keyword in tail.raw_text.lower()


# -- initial prompt end-to-end: term in the seed -----------------------------


@pytest.mark.skipif(not WAV_TERMS.exists(), reason="test audio not generated")
def test_prompt_term_does_not_break_transcription():
    """Seeding 'Cloudflare' must keep the sentence intact (and may fix its spelling)."""
    baseline = _make_engine().transcribe(str(WAV_TERMS))

    seeded_engine = _make_engine(replacements={"клаудфлер": "Cloudflare"})
    assert seeded_engine.initial_prompt() == "Cloudflare."
    seeded = seeded_engine.transcribe(str(WAV_TERMS))

    for keyword in ("deploy", "commit", "pipeline"):
        assert keyword in seeded.raw_text.lower(), (
            f"prompt broke transcription:\n base:   {baseline.raw_text}"
            f"\n seeded: {seeded.raw_text}"
        )
    # Informational: did the seed fix the brand spelling?
    print(
        f"\nbaseline: {baseline.raw_text}\nseeded:   {seeded.raw_text}\n"
        f"cloudflare verbatim: base={'Cloudflare' in baseline.raw_text} "
        f"seeded={'Cloudflare' in seeded.raw_text}"
    )
