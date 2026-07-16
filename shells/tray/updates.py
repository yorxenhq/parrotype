"""Weekly update check: one anonymous GitHub API request, quiet on failure.

- runs at most once every 7 days, 60s after startup, in a daemon thread;
- any network failure is silent (debug log only);
- no popups, no auto-download: the result is a tray menu item + About line.

Qt-free on purpose — everything here is testable headless. GUI wiring
(signal marshalling, the menu item) lives in shells/tray/app.py.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from typing import Callable

from core import APP_VERSION, Config

log = logging.getLogger(__name__)

RELEASES_API_URL = "https://api.github.com/repos/yorxenhq/parrotype/releases/latest"
RELEASES_PAGE_URL = "https://github.com/yorxenhq/parrotype/releases/latest"
CHECK_INTERVAL = timedelta(days=7)
STARTUP_DELAY_MS = 60_000
TIMEOUT_S = 5.0
_MAX_BODY = 1_000_000  # the /releases/latest JSON is a few KB; hard cap anyway


def parse_version(tag: str) -> tuple[int, ...] | None:
    """'v1.2.3' / '1.2' -> (1, 2, 3) / (1, 2). None when not a version."""
    core_part = tag.strip().lstrip("vV").split("-")[0].split("+")[0]
    if not core_part:
        return None
    parts: list[int] = []
    for piece in core_part.split("."):
        if not piece.isdigit():
            return None
        parts.append(int(piece))
    return tuple(parts)


def is_newer(remote_tag: str, current: str = APP_VERSION) -> bool:
    """True when remote_tag is a strictly newer version than current."""
    remote = parse_version(remote_tag)
    local = parse_version(current)
    if remote is None or local is None:
        return False  # garbage tags never trigger the notice
    width = max(len(remote), len(local))
    remote_p = remote + (0,) * (width - len(remote))   # 1.1 == 1.1.0
    local_p = local + (0,) * (width - len(local))
    return remote_p > local_p


def should_check(config: Config, now: datetime | None = None) -> bool:
    """True when the toggle is on and the last successful check is >= 7 days old."""
    if not config.check_updates:
        return False
    if not config.last_update_check:
        return True
    try:
        last = datetime.fromisoformat(config.last_update_check)
    except ValueError:
        return True  # malformed stamp counts as "never checked"
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return now - last >= CHECK_INTERVAL


def fetch_latest_tag(timeout: float = TIMEOUT_S) -> str | None:
    """One anonymous GET; returns the latest release tag, None on ANY failure."""
    req = urllib.request.Request(
        RELEASES_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Parrotype/{APP_VERSION}",  # GitHub rejects UA-less requests
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read(_MAX_BODY).decode("utf-8"))
        tag = data.get("tag_name")
        return tag if isinstance(tag, str) and tag else None
    except Exception as exc:  # offline, DNS, 403 rate-limit, bad JSON — all silent
        log.debug("Update check failed quietly: %s", exc)
        return None


def apply_result(config: Config, tag: str | None) -> str | None:
    """Persist a fetch outcome; return the newer tag or None.

    A failed fetch (tag=None) does NOT touch last_update_check — the next
    launch retries, so a week offline can't silence updates for another week.
    Call from the GUI thread only (mutates and saves config).
    """
    if tag is None:
        return None
    config.last_update_check = datetime.now(timezone.utc).isoformat(timespec="seconds")
    config.update_available_tag = tag if is_newer(tag) else ""
    config.save()
    return config.update_available_tag or None


def start_background_check(
    config: Config, on_result: Callable[[str], None]
) -> threading.Thread | None:
    """Fetch in a daemon thread when a check is due; returns None when skipped.

    on_result is called FROM THE WORKER THREAD with the raw tag ("" on
    failure) — pass a Qt signal's emit to hop onto the GUI thread. Config is
    not touched here: mutation + save happen in apply_result on the GUI side.
    """
    if not should_check(config):
        return None

    def worker() -> None:
        on_result(fetch_latest_tag() or "")

    thread = threading.Thread(target=worker, name="update-check", daemon=True)
    thread.start()
    return thread


def open_release_page() -> None:
    webbrowser.open(RELEASES_PAGE_URL)
