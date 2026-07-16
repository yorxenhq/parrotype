"""Application configuration: dataclass + JSON persistence in %APPDATA%/Parrotype."""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "Parrotype"
APP_VERSION = "0.1.0"

log = logging.getLogger(__name__)


def app_data_dir() -> Path:
    """Directory for config/history/logs (created on demand)."""
    base = os.environ.get("PARROTYPE_DATA_DIR")
    if base:
        path = Path(base)
    else:
        appdata = os.environ.get("APPDATA") or str(Path.home())
        path = Path(appdata) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Config:
    """All user-facing settings. Persisted as JSON."""

    # Model
    model_size: str = "small"          # tiny | base | small | medium | large-v3
    device: str = "auto"               # auto | cuda | cpu
    compute_type: str = "auto"         # auto | float16 | int8_float16 | int8
    language: str = "auto"             # auto | ru | en

    # Audio
    input_device: int | None = None    # None = system default
    sample_rate: int = 16000

    # Hotkeys ("+"-separated key names, e.g. "ctrl+alt")
    hotkey_ptt: str = "ctrl+alt"       # hold to talk
    hotkey_toggle: str = "ctrl+shift+space"  # press to start/stop (disjoint from PTT)

    # Behaviour
    insert_method: str = "auto"        # auto (type short / clipboard long) | clipboard
    ui_language: str = "auto"          # auto (system) | ru | en
    first_run_done: bool = False       # first-run wizard completed
    autostart: bool = False
    sound_ticks: bool = True
    keep_history: bool = True
    history_limit: int = 50

    # Post-filter dictionary: {"heard": "written"}
    replacements: dict[str, str] = field(default_factory=dict)

    # Free-form recognition context appended to the whisper initial_prompt
    # (dictionary targets are always included automatically). Empty = off.
    recognition_context: str = ""

    # -- persistence ---------------------------------------------------

    @staticmethod
    def path() -> Path:
        return app_data_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        path = cls.path()
        if not path.exists():
            # First run: default model picked from measured latency on the
            # reference machine (see README benchmark): GPU runs
            # `large-v3-turbo` in ~0.8s per 13.5s of audio (best quality per
            # second); CPU is only comfortable at `small`.
            cfg = cls()
            cfg.model_size = "large-v3-turbo" if cuda_available() else "small"
            return cfg
        try:
            raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error("Failed to read config %s: %s — using defaults", path, exc)
            return cls()
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        path = self.path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(dataclasses.asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    # -- hardware resolution -------------------------------------------

    def resolve_device(self) -> tuple[str, str]:
        """Resolve (device, compute_type) honouring 'auto' values."""
        device = self.device
        if device == "auto":
            device = "cuda" if cuda_available() else "cpu"
        compute = self.compute_type
        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"
        return device, compute


def cuda_available() -> bool:
    """True when ctranslate2 reports a usable CUDA device."""
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception as exc:  # pragma: no cover - defensive: any backend error means "no CUDA"
        log.debug("CUDA probe failed: %s", exc)
        return False
