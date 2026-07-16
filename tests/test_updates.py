"""Update check: version comparison, weekly throttle, kill switch, persistence."""

from datetime import datetime, timedelta, timezone

import pytest

from core.config import Config
from shells.tray import updates


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PARROTYPE_DATA_DIR", str(tmp_path))
    return tmp_path


# -- version comparison ---------------------------------------------------

@pytest.mark.parametrize(
    ("remote", "current", "newer"),
    [
        ("1.0.0", "0.9", True),
        ("1.0.1", "1.0.0", True),
        ("1.1", "1.0.1", True),
        ("v1.0.1", "1.0.0", True),       # with v prefix
        ("1.0.1", "v1.0.0", True),
        ("1.0.0", "1.0.0", False),       # equal
        ("v1.0.0", "1.0.0", False),
        ("1.0", "1.0.0", False),         # 1.0 == 1.0.0
        ("0.9", "1.0.0", False),         # older
        ("banana", "1.0.0", False),      # garbage tag never triggers
        ("", "1.0.0", False),
    ],
)
def test_is_newer(remote, current, newer):
    assert updates.is_newer(remote, current) is newer


# -- weekly throttle --------------------------------------------------------

def _stamp(days_ago: float) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(days=days_ago)
    ).isoformat(timespec="seconds")


def test_should_check_when_never_checked():
    assert updates.should_check(Config()) is True


def test_should_check_throttles_fresh_stamp():
    assert updates.should_check(Config(last_update_check=_stamp(3))) is False


def test_should_check_after_seven_days():
    assert updates.should_check(Config(last_update_check=_stamp(8))) is True


def test_should_check_malformed_stamp_counts_as_never():
    assert updates.should_check(Config(last_update_check="not-a-date")) is True


# -- kill switch: zero requests ----------------------------------------------

def test_disabled_toggle_makes_no_request(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(updates, "fetch_latest_tag", lambda *a, **k: calls.append(1))
    thread = updates.start_background_check(
        Config(check_updates=False), lambda tag: None
    )
    assert thread is None
    assert calls == []


def test_fresh_stamp_makes_no_request(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(updates, "fetch_latest_tag", lambda *a, **k: calls.append(1))
    assert updates.start_background_check(
        Config(last_update_check=_stamp(1)), lambda tag: None
    ) is None
    assert calls == []


def test_due_check_fetches_and_reports(monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest_tag", lambda *a, **k: "v9.9.9")
    got: list[str] = []
    thread = updates.start_background_check(Config(), got.append)
    assert thread is not None
    thread.join(timeout=5)
    assert got == ["v9.9.9"]


# -- persistence of the outcome ------------------------------------------------

def test_apply_result_stores_newer_tag():
    cfg = Config()
    assert updates.apply_result(cfg, "v99.0.0") == "v99.0.0"
    assert cfg.update_available_tag == "v99.0.0"
    assert cfg.last_update_check != ""
    assert Config.load().update_available_tag == "v99.0.0"   # survives restart


def test_apply_result_clears_stale_tag_when_not_newer():
    cfg = Config(update_available_tag="v0.5")
    assert updates.apply_result(cfg, "0.1.0") is None
    assert cfg.update_available_tag == ""
    assert cfg.last_update_check != ""


def test_apply_result_failure_keeps_stamp_for_retry():
    cfg = Config(last_update_check="")
    assert updates.apply_result(cfg, None) is None
    assert cfg.last_update_check == ""   # retries next launch, not in 7 days
