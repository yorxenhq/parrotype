"""Insert text into the active window without losing a dictation.

Primary path: direct typing via SendInput KEYEVENTF_UNICODE — the
clipboard is not touched at all (layout-independent, no restore races).

Fallback for long texts (> MAX_TYPED_CHARS): clipboard + Ctrl+V, hardened:
  - waits for physical modifier keys to be released before injecting
    Ctrl+V (a held Ctrl/Alt would turn it into a different shortcut)
  - restores the previous clipboard ONLY if the clipboard still contains
    our text (if the user copied something meanwhile, theirs wins)

No-loss guarantee: on any failure the recognized text is LEFT on the
clipboard and InsertResult.ok=False is returned so the UI can tell the
user to press Ctrl+V manually. The dictation is never dropped.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pyperclip

from shells.tray.wininput import (
    InjectionAborted,
    send_paste,
    type_text,
    wait_modifiers_released,
)

log = logging.getLogger(__name__)

MAX_TYPED_CHARS = 1000   # longer texts go through the clipboard fallback
RESTORE_DELAY_S = 1.0    # let the target app read the clipboard before restoring
SETTLE_DELAY_S = 0.10    # let the clipboard update propagate before Ctrl+V
MODIFIER_TIMEOUT_S = 2.0


@dataclass
class InsertResult:
    ok: bool
    method: str          # "typed" | "clipboard" | "clipboard-manual"
    message: str = ""


def insert_text(
    text: str,
    restore_clipboard: bool = True,
    method: str = "auto",
    abort_check=None,
) -> InsertResult:
    """Insert `text` into the focused window. Never raises; never loses text.

    method: "auto" = type short texts, clipboard for long ones;
            "clipboard" = always clipboard+Ctrl+V (for target apps whose
            edit controls mishandle fast injected typing, e.g. Win11 Notepad).
    abort_check: optional callback (test harnesses) — typing stops
            immediately when it returns False (target lost focus).
    Runs synchronously (typing ~0.5s per 300 chars; fallback ~1.5s);
    call from a worker thread.
    """
    if not text:
        return InsertResult(ok=True, method="typed")
    try:
        if method != "clipboard" and len(text) <= MAX_TYPED_CHARS:
            if not wait_modifiers_released(MODIFIER_TIMEOUT_S):
                # Held PTT/AltGr keys would combine with typed keys.
                pyperclip.copy(text)
                return InsertResult(
                    ok=False,
                    method="clipboard-manual",
                    message="modifier keys held down",
                )
            type_text(text, abort_check=abort_check)
            return InsertResult(ok=True, method="typed")
        return _clipboard_fallback(text, restore_clipboard)
    except InjectionAborted as exc:
        # Test-harness veto: no clipboard parking, just report.
        return InsertResult(ok=False, method="aborted", message=str(exc))
    except Exception as exc:  # no-loss guarantee: park the text on the clipboard
        log.exception("Insert failed; leaving text on the clipboard")
        try:
            pyperclip.copy(text)
        except pyperclip.PyperclipException:
            log.exception("Could not even copy the text to the clipboard")
        return InsertResult(ok=False, method="clipboard-manual", message=str(exc))


def _clipboard_fallback(text: str, restore_clipboard: bool) -> InsertResult:
    previous: str | None = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException as exc:
            log.warning("Could not read clipboard for restore: %s", exc)

    # A physically held Ctrl/Alt/Shift/Win would corrupt the injected Ctrl+V.
    if not wait_modifiers_released(MODIFIER_TIMEOUT_S):
        pyperclip.copy(text)
        return InsertResult(
            ok=False,
            method="clipboard-manual",
            message="modifier keys held down",
        )

    pyperclip.copy(text)
    time.sleep(SETTLE_DELAY_S)
    send_paste()
    time.sleep(RESTORE_DELAY_S)

    if restore_clipboard and previous is not None:
        try:
            # Restore only if the clipboard still holds OUR text; if the
            # user copied something else during the window, keep theirs.
            if pyperclip.paste() == text:
                pyperclip.copy(previous)
        except pyperclip.PyperclipException as exc:
            log.warning("Could not restore clipboard: %s", exc)
    return InsertResult(ok=True, method="clipboard")


def paste_text(text: str, restore_clipboard: bool = True) -> None:
    """Backward-compatible wrapper around insert_text."""
    insert_text(text, restore_clipboard)
