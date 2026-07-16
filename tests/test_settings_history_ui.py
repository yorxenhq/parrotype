"""History page UI: card click copies, trash deletes, clear-all confirm.

Runs on the offscreen Qt platform — no windows, no input injection.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def dialog(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("PARROTYPE_DATA_DIR", str(tmp_path))
    from core import Config, History
    from shells.tray.settings import SettingsDialog

    history = History(limit=50)
    history.add("first dictation", 3.0)
    history.add("second dictation", 65.0)
    history.add("third dictation", 0.4)
    dlg = SettingsDialog(Config(), history)
    yield dlg
    dlg.deleteLater()
    qapp.processEvents()


def _cards(dialog):
    from shells.tray.settings import HistoryCard

    return [
        dialog._hist_vbox.itemAt(i).widget()
        for i in range(dialog._hist_vbox.count())
        if isinstance(dialog._hist_vbox.itemAt(i).widget(), HistoryCard)
    ]


def test_click_copies_to_clipboard(qapp, dialog):
    cards = _cards(dialog)
    assert [c.entry.text for c in cards] == [
        "third dictation", "second dictation", "first dictation",
    ]  # newest first
    QTest.mouseClick(cards[1], Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == "second dictation"
    assert cards[1].property("copied") is True          # 1.2s accent flash armed
    QTest.mouseClick(cards[0], Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == "third dictation"


def test_trash_deletes_the_right_entry(qapp, dialog):
    cards = _cards(dialog)
    QTest.mouseClick(cards[1].trash_btn, Qt.MouseButton.LeftButton)  # "second dictation"
    assert [e.text for e in dialog.history.entries] == [
        "third dictation", "first dictation",
    ]
    assert [c.entry.text for c in _cards(dialog)] == [
        "third dictation", "first dictation",
    ]  # cards rebuilt, indices in sync


def test_keyboard_delete_removes_focused_card(qapp, dialog):
    cards = _cards(dialog)
    QTest.keyClick(cards[0], Qt.Key.Key_Delete)          # newest entry
    assert [e.text for e in dialog.history.entries] == [
        "second dictation", "first dictation",
    ]


def test_clear_all_needs_inline_confirmation(qapp, dialog):
    QTest.mouseClick(dialog.clear_btn, Qt.MouseButton.LeftButton)
    assert dialog.clear_btn.isHidden()
    assert not dialog.clear_confirm.isHidden()
    dialog._cancel_clear()                               # "Keep them" path
    assert dialog.history.entries                        # nothing deleted
    dialog._ask_clear()
    dialog._confirm_clear()                              # "Yes, delete" path
    assert dialog.history.entries == []
    assert not dialog.clear_btn.isEnabled()
    assert not dialog.hist_empty_label.isHidden()
    assert dialog.hist_scroll.isHidden()
