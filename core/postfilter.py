"""Post-filter: user dictionary of replacements ("heard" -> "written").

Applied to the raw STT output. Matching is case-insensitive on word
boundaries so that e.g. "клод" -> "Claude" works mid-sentence, while
substrings inside other words are left alone.
"""

from __future__ import annotations

import re


class PostFilter:
    def __init__(self, replacements: dict[str, str] | None = None):
        self._replacements: dict[str, str] = dict(replacements or {})
        self._pattern: re.Pattern[str] | None = None
        self._lookup: dict[str, str] = {}
        self._compile()

    def _compile(self) -> None:
        if not self._replacements:
            self._pattern = None
            self._lookup = {}
            return
        # Longest keys first so "гит хаб" wins over "гит".
        keys = sorted(self._replacements, key=len, reverse=True)
        self._lookup = {k.lower(): v for k, v in self._replacements.items()}
        # \b does not work reliably around Cyrillic/Latin boundaries in all
        # cases, so use explicit non-word-character lookarounds.
        alt = "|".join(re.escape(k) for k in keys)
        self._pattern = re.compile(
            rf"(?<![\w-])({alt})(?![\w-])", re.IGNORECASE | re.UNICODE
        )

    def apply(self, text: str) -> str:
        if not text or self._pattern is None:
            return text
        return self._pattern.sub(
            lambda m: self._lookup.get(m.group(1).lower(), m.group(1)), text
        )

    @property
    def replacements(self) -> dict[str, str]:
        return dict(self._replacements)
