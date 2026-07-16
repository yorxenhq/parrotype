"""Local dictation history: last N entries, stored as JSON. No cloud, ever."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from core.config import app_data_dir

log = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    text: str
    timestamp: float          # unix seconds
    audio_seconds: float
    raw: str = ""             # pre-polish transcript ("" = same as text)


class History:
    def __init__(self, limit: int = 50, path: Path | None = None):
        self.limit = limit
        self.path = path or (app_data_dir() / "history.json")
        self._entries: list[HistoryEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._entries = [HistoryEntry(**item) for item in raw][-self.limit:]
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            log.error("Failed to load history: %s", exc)
            self._entries = []

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([asdict(e) for e in self._entries], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def add(self, text: str, audio_seconds: float = 0.0, raw: str = "") -> None:
        # A polished dictation keeps its raw transcript: polish must never
        # be able to lose what the user actually said.
        self._entries.append(
            HistoryEntry(
                text=text, timestamp=time.time(),
                audio_seconds=audio_seconds,
                raw=raw if raw != text else "",
            )
        )
        self._entries = self._entries[-self.limit:]
        self._save()

    def remove(self, index: int) -> None:
        """Remove by index in `entries` order (newest first)."""
        if 0 <= index < len(self._entries):
            del self._entries[len(self._entries) - 1 - index]
            self._save()

    def clear(self) -> None:
        self._entries = []
        self._save()

    @property
    def entries(self) -> list[HistoryEntry]:
        """Newest first."""
        return list(reversed(self._entries))

    @property
    def last(self) -> HistoryEntry | None:
        return self._entries[-1] if self._entries else None
