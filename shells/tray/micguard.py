"""Microphone endpoint guard: detect/lift a system-level mute (pycaw).

An endpoint-level mute is invisible on the main Windows Settings page and
cost a long debugging session in live use — the app surfaces it instead.

THREADING (the root cause of the "random c0000005 on transcribe" saga):
comtypes COM pointers must be created, used, released AND garbage-collected
on the same COM-initialized thread. The old implementation created them on
whatever short-lived thread asked (startup self-check, recording start) and
let Python's GC release them later — from an arbitrary thread, after the
creating thread's COM apartment was torn down. That access-violated inside
_ctypes.pyd at unpredictable moments; big whisper models made it frequent
simply by allocating more (GC ran more often). Every pycaw call now runs on
ONE long-lived COM worker thread, and gc.collect() runs there after each
call so every COM Release happens in the right apartment, deterministically.
"""

from __future__ import annotations

import gc
import logging
import queue
import threading
from typing import Any, Callable

log = logging.getLogger(__name__)

_CALL_TIMEOUT_S = 3.0

_requests: "queue.Queue[tuple[Callable[[], Any], queue.Queue]]" = queue.Queue()
_thread_started = threading.Lock()
_thread: threading.Thread | None = None


def _com_loop() -> None:
    import comtypes

    comtypes.CoInitialize()
    log.debug("COM worker thread started")
    while True:
        func, reply = _requests.get()
        try:
            result: tuple[bool, Any] = (True, func())
        except Exception as exc:  # reported to the caller, never raised here
            result = (False, exc)
        finally:
            # Drop this call's COM references NOW, on this thread, while the
            # apartment is alive — never from the GC on a foreign thread.
            gc.collect()
        reply.put(result)


def _run_on_com_thread(func: Callable[[], Any]) -> Any:
    """Execute func on the COM worker thread; raise its exception here."""
    global _thread
    with _thread_started:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(
                target=_com_loop, daemon=True, name="parrotype-com"
            )
            _thread.start()
    reply: queue.Queue = queue.Queue()
    _requests.put((func, reply))
    ok, value = reply.get(timeout=_CALL_TIMEOUT_S)
    if not ok:
        raise value
    return value


def _query_mute() -> bool | None:
    """Runs ON the COM thread: build, read, release — nothing escapes."""
    import comtypes
    from ctypes import POINTER, cast

    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    mic = AudioUtilities.GetMicrophone()
    if mic is None:
        return None
    interface = mic.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))
    return bool(volume.GetMute())


def _lift_mute() -> bool:
    """Runs ON the COM thread."""
    import comtypes
    from ctypes import POINTER, cast

    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    mic = AudioUtilities.GetMicrophone()
    if mic is None:
        return False
    interface = mic.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))
    volume.SetMute(0, None)
    return not bool(volume.GetMute())


def default_mic_muted() -> bool | None:
    """True/False for the default capture endpoint; None when undetectable."""
    try:
        return _run_on_com_thread(_query_mute)
    except Exception as exc:
        log.debug("Mic mute query failed: %s", exc)
        return None


def unmute_default_mic() -> bool:
    """Lift the endpoint mute. Returns True on success."""
    try:
        return bool(_run_on_com_thread(_lift_mute))
    except Exception as exc:
        log.error("Mic unmute failed: %s", exc)
        return False
