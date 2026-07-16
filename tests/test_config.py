import json

import pytest

from core.config import Config


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PARROTYPE_DATA_DIR", str(tmp_path))
    return tmp_path


def test_defaults_when_no_file():
    from core.config import cuda_available

    cfg = Config.load()
    # First-run default is hardware-dependent (picked from measured latency).
    expected = "medium" if cuda_available() else "small"
    assert cfg.model_size == expected
    assert cfg.language == "auto"
    assert cfg.history_limit == 50


def test_save_and_load_roundtrip(data_dir):
    cfg = Config.load()
    cfg.model_size = "medium"
    cfg.replacements = {"клод": "Claude"}
    cfg.save()

    loaded = Config.load()
    assert loaded.model_size == "medium"
    assert loaded.replacements == {"клод": "Claude"}
    assert (data_dir / "config.json").exists()


def test_corrupt_config_falls_back_to_defaults(data_dir):
    (data_dir / "config.json").write_text("{not json", encoding="utf-8")
    cfg = Config.load()
    assert cfg.model_size == "small"


def test_unknown_keys_ignored(data_dir):
    (data_dir / "config.json").write_text(
        json.dumps({"model_size": "base", "future_option": 42}), encoding="utf-8"
    )
    cfg = Config.load()
    assert cfg.model_size == "base"


def test_resolve_device_cpu_forced():
    cfg = Config(device="cpu", compute_type="auto")
    assert cfg.resolve_device() == ("cpu", "int8")
