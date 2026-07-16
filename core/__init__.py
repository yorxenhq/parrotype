"""Parrotype core: audio capture -> VAD -> STT -> post-filter -> text.

UI-independent speech engine. Import as a library:

    from core import Engine, Config
    engine = Engine(Config.load())
    result = engine.transcribe("audio.wav")
    print(result.text)
"""

from core.config import Config, APP_NAME, APP_VERSION
from core.engine import Engine, TranscriptionResult
from core.postfilter import PostFilter
from core.history import History
from core.audio import Recorder, list_input_devices

__all__ = [
    "Config",
    "Engine",
    "TranscriptionResult",
    "PostFilter",
    "History",
    "Recorder",
    "list_input_devices",
    "APP_NAME",
    "APP_VERSION",
]
