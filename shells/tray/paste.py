"""Insert text into the active window: clipboard + Ctrl+V, restore clipboard."""

from __future__ import annotations

import logging
import time

import pyperclip

from shells.tray.wininput import send_paste

log = logging.getLogger(__name__)

RESTORE_DELAY_S = 0.60   # let the target app read the clipboard before restoring
SETTLE_DELAY_S = 0.10    # let the clipboard update propagate before Ctrl+V


def paste_text(text: str, restore_clipboard: bool = True) -> None:
    """Put `text` on the clipboard, send Ctrl+V, then restore the old clipboard.

    Runs synchronously (~0.4s); call from a worker thread.
    Only text clipboard content is preserved (v1 limitation).
    """
    previous: str | None = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException as exc:
            log.warning("Could not read clipboard for restore: %s", exc)

    pyperclip.copy(text)
    time.sleep(SETTLE_DELAY_S)
    send_paste()
    time.sleep(RESTORE_DELAY_S)

    if restore_clipboard and previous is not None:
        try:
            pyperclip.copy(previous)
        except pyperclip.PyperclipException as exc:
            log.warning("Could not restore clipboard: %s", exc)
