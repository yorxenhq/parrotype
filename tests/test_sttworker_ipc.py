"""Unit tests for the STT worker IPC framing and bench-aware model options."""

import json
import os
import struct
import threading

import pytest

from core.sttworker import read_frame, write_frame


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PARROTYPE_DATA_DIR", str(tmp_path))
    return tmp_path


def _pipe_pair():
    r, w = os.pipe()
    if os.name == "nt":
        import msvcrt

        msvcrt.setmode(r, os.O_BINARY)
        msvcrt.setmode(w, os.O_BINARY)
    return r, w


def test_frame_roundtrip_plain():
    r, w = _pipe_pair()
    write_frame(w, {"cmd": "ping", "note": "привет"})
    header, payload = read_frame(r)
    assert header["cmd"] == "ping"
    assert header["note"] == "привет"
    assert payload == b""
    os.close(r), os.close(w)


def test_frame_roundtrip_with_payload():
    r, w = _pipe_pair()
    blob = os.urandom(300_000)  # bigger than one pipe buffer

    t = threading.Thread(target=write_frame, args=(w, {"cmd": "transcribe"}, blob))
    t.start()
    header, payload = read_frame(r)
    t.join()
    assert header["payload"] == len(blob)
    assert payload == blob
    os.close(r), os.close(w)


def test_frame_eof_raises():
    r, w = _pipe_pair()
    os.write(w, struct.pack("<I", 100) + b'{"cmd": "truncated"')  # short frame
    os.close(w)
    with pytest.raises(EOFError):
        read_frame(r)
    os.close(r)


def test_frame_rejects_garbage_header():
    r, w = _pipe_pair()
    raw = b"\x0b\x00\x00\x00" + b"not json at"
    os.write(w, raw)
    os.close(w)
    with pytest.raises(json.JSONDecodeError):
        read_frame(r)
    os.close(r)


def test_bench_overrides_model_options():
    from shells.tray.modelpicker import CPU_OPTIONS, _apply_bench

    small = next(o for o in CPU_OPTIONS if o.name == "small")

    measured = _apply_bench(small, {"latency": 2.31, "audio": 13.5})
    assert measured.measured is True
    assert measured.sec == "2.3"
    assert measured.unstable is False

    crashed = _apply_bench(small, {"unstable": True})
    assert crashed.unstable is True

    untouched = _apply_bench(small, None)
    assert untouched == small
