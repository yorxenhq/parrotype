"""End-to-end engine test on synthesized speech (tiny model, CPU).

Slow-ish (~15s incl. model load on first run); still part of the default
suite because it exercises the real STT path.
"""

from pathlib import Path

import pytest

from core import Config, Engine

WAV = Path(__file__).parent / "data" / "test_en.wav"


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PARROTYPE_DATA_DIR", str(tmp_path))


@pytest.fixture(scope="module")
def engine():
    cfg = Config(model_size="tiny", device="cpu", compute_type="int8", language="en")
    return Engine(cfg)


@pytest.mark.skipif(not WAV.exists(), reason="test audio not generated")
def test_transcribes_keywords(engine):
    result = engine.transcribe(str(WAV))
    text = result.text.lower()
    for keyword in ("settings", "latency", "quick brown fox", "offline", "whisper"):
        assert keyword in text, f"missing {keyword!r} in: {result.text}"
    assert result.language == "en"
    assert 10 < result.audio_seconds < 20
    assert result.latency_seconds > 0


@pytest.mark.skipif(not WAV.exists(), reason="test audio not generated")
def test_postfilter_applied_to_transcript(engine):
    engine.config.replacements = {
        "whisper": "Whisper-X",
        "latency table": "LATENCY-TABLE",
    }
    engine.reload_postfilter()
    result = engine.transcribe(str(WAV))
    assert "Whisper-X" in result.text
    assert "LATENCY-TABLE" in result.text
    assert "Whisper-X" not in result.raw_text     # raw stays unfiltered
    engine.config.replacements = {}
    engine.reload_postfilter()
