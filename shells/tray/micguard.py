"""Microphone endpoint guard: detect/lift a system-level mute (pycaw).

An endpoint-level mute is invisible on the main Windows Settings page and
cost a long debugging session in live use — the app surfaces it instead.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _endpoint_volume():
    import comtypes
    from ctypes import POINTER, cast

    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    try:
        comtypes.CoInitialize()          # safe to call repeatedly per thread
    except OSError:
        pass
    mic = AudioUtilities.GetMicrophone()
    if mic is None:
        return None
    interface = mic.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def default_mic_muted() -> bool | None:
    """True/False for the default capture endpoint; None when undetectable."""
    try:
        volume = _endpoint_volume()
        if volume is None:
            return None
        return bool(volume.GetMute())
    except Exception as exc:
        log.debug("Mic mute query failed: %s", exc)
        return None


def unmute_default_mic() -> bool:
    """Lift the endpoint mute. Returns True on success."""
    try:
        volume = _endpoint_volume()
        if volume is None:
            return False
        volume.SetMute(0, None)
        return not bool(volume.GetMute())
    except Exception as exc:
        log.error("Mic unmute failed: %s", exc)
        return False
