"""Global hotkeys on top of the in-repo WH_KEYBOARD_LL hook (wininput).

Two simultaneous bindings:
  - push-to-talk: hold combo -> record while held
  - toggle: press combo -> start, press again -> stop
Esc is armed only while recording (cancel).

Hook events arrive on the hook thread; Qt signals are emitted from there
and delivered to the GUI thread via queued connections.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from shells.tray.wininput import KeyboardHook, parse_combo, validate_combo

__all__ = ["HotkeyManager", "validate_combo"]

log = logging.getLogger(__name__)

_VK_ESC = 0x1B


class HotkeyManager(QObject):
    ptt_pressed = Signal()
    ptt_released = Signal()
    toggle_triggered = Signal()
    cancel_pressed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._ptt: frozenset[int] = frozenset()
        self._toggle: frozenset[int] = frozenset()
        self._pressed: set[int] = set()
        self._ptt_down = False
        self._toggle_fired = False
        self._cancel_armed = False
        self._paused = False
        self._hook: KeyboardHook | None = None

    # -- lifecycle -------------------------------------------------------

    def bind(self, ptt_combo: str, toggle_combo: str) -> None:
        """(Re)register hotkey combos. Invalid combos are logged and skipped."""
        self._ptt = self._parse(ptt_combo, "PTT")
        self._toggle = self._parse(toggle_combo, "toggle")
        self._pressed.clear()
        self._ptt_down = False
        self._toggle_fired = False
        if self._hook is None:
            self._hook = KeyboardHook(self._on_key)
            self._hook.start()

    @staticmethod
    def _parse(combo: str, label: str) -> frozenset[int]:
        if not combo:
            return frozenset()
        try:
            return parse_combo(combo)
        except ValueError as exc:
            log.error("Cannot bind %s hotkey %r: %s", label, combo, exc)
            return frozenset()

    def unbind(self) -> None:
        if self._hook is not None:
            self._hook.stop()
            self._hook = None
        self._pressed.clear()
        self._ptt_down = False
        self._toggle_fired = False
        self._cancel_armed = False

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    @property
    def paused(self) -> bool:
        return self._paused

    # -- Esc-cancel (armed only while recording) ---------------------------

    def arm_cancel(self) -> None:
        self._cancel_armed = True

    def disarm_cancel(self) -> None:
        self._cancel_armed = False

    # -- hook-thread event handling ------------------------------------------

    def _on_key(self, vk: int, down: bool) -> None:
        if down:
            if vk in self._pressed:
                return                      # key auto-repeat, not a transition
            self._pressed.add(vk)
            self._on_transition_down(vk)
        else:
            self._pressed.discard(vk)
            self._on_transition_up(vk)

    def _on_transition_down(self, vk: int) -> None:
        if self._cancel_armed and vk == _VK_ESC:
            self.cancel_pressed.emit()
            return
        if self._paused:
            return
        # Toggle first: it may be a superset of the PTT combo.
        if self._toggle and vk in self._toggle and self._toggle <= self._pressed:
            if not self._toggle_fired:
                self._toggle_fired = True
                self.toggle_triggered.emit()
            return
        if self._ptt and vk in self._ptt and self._ptt <= self._pressed:
            if not self._ptt_down:
                self._ptt_down = True
                self.ptt_pressed.emit()

    def _on_transition_up(self, vk: int) -> None:
        if self._toggle_fired and vk in self._toggle:
            self._toggle_fired = False
        if self._ptt_down and vk in self._ptt:
            self._ptt_down = False
            self.ptt_released.emit()
