"""Reliability package tests: device filtering, i18n layer, mute guard."""

import pytest

from core.audio import is_virtual_device
from shells.tray import i18n


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PARROTYPE_DATA_DIR", str(tmp_path))


# -- virtual device filter -----------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Steam Streaming Microphone",
        "Microsoft Sound Mapper - Input",
        "Voice Changer Virtual Audio Device (WDM)",
        "CABLE Output (VB-Audio Virtual Cable)",
        "Voicemeeter Out B1",
        "Stereo Mix (Realtek(R) Audio)",
        "Virtual Desktop Audio",
    ],
)
def test_virtual_devices_detected(name):
    assert is_virtual_device(name)


@pytest.mark.parametrize(
    "name",
    [
        "Microphone Array (Realtek(R) Audio)",
        "Headset Microphone (Jabra)",
        "USB Audio Device",
        "Microphone (Blue Yeti)",
    ],
)
def test_real_devices_pass(name):
    assert not is_virtual_device(name)


def test_pick_input_device_prefers_valid_preferred(monkeypatch):
    from core import audio

    monkeypatch.setattr(
        audio, "list_input_devices",
        lambda skip_virtual=False: [(0, "Steam Streaming Microphone"), (3, "USB Mic")],
    )
    assert audio.pick_input_device(preferred=3) == 3
    # stale preferred id (device unplugged) is not honored
    assert audio.pick_input_device(preferred=99) != 99


# -- i18n layer ---------------------------------------------------------------


def test_i18n_ru_en_roundtrip():
    i18n.set_language("ru")
    assert i18n.tr("tray.ready") == "Готов"
    i18n.set_language("en")
    assert i18n.tr("tray.ready") == "Ready"


def test_i18n_formatting_and_fallback():
    i18n.set_language("en")
    assert "42" in i18n.tr("pill.downloading_model", pct=42)
    # unknown key falls back to the key itself (and logs)
    assert i18n.tr("no.such.key") == "no.such.key"


def test_i18n_auto_resolves():
    i18n.set_language("auto")
    assert i18n.current_language() in ("ru", "en")


def test_i18n_all_keys_have_both_languages():
    for key, entry in i18n._STRINGS.items():
        assert "en" in entry, f"{key} missing en"
        assert "ru" in entry, f"{key} missing ru"


# -- mute guard (queries only; never mutates the user's endpoint) -------------


def test_default_mic_muted_returns_bool_or_none():
    from shells.tray import micguard

    result = micguard.default_mic_muted()
    assert result in (True, False, None)
