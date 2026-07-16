import pytest

from core.history import History


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PARROTYPE_DATA_DIR", str(tmp_path))
    return tmp_path


def test_add_and_read():
    h = History(limit=50)
    h.add("первая диктовка", 3.5)
    h.add("вторая", 1.0)
    assert h.entries[0].text == "вторая"      # newest first
    assert h.last.text == "вторая"
    assert h.entries[1].audio_seconds == 3.5


def test_limit_enforced():
    h = History(limit=3)
    for i in range(5):
        h.add(f"текст {i}")
    assert len(h.entries) == 3
    assert h.entries[0].text == "текст 4"


def test_persistence(tmp_path):
    h1 = History(limit=50)
    h1.add("сохранённая запись")
    h2 = History(limit=50)
    assert h2.last.text == "сохранённая запись"


def test_remove_and_clear():
    h = History(limit=50)
    h.add("a")
    h.add("b")
    h.remove(0)                                # newest-first index -> removes "b"
    assert len(h.entries) == 1
    assert h.entries[0].text == "a"
    h.clear()
    assert h.entries == []
    assert h.last is None
