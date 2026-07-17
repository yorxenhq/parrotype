"""Client for the STT worker process: Engine-compatible, crash-proof.

IsolatedEngine mirrors the public surface of core.engine.Engine that the
shells use (is_model_cached / ensure_model / load_model / warm_up /
transcribe / reload_postfilter / model_loaded), but runs the native
decode in a separate worker process (core.sttworker). If the worker dies
mid-request — the ctranslate2 CPU int8 kernels are known to
access-violate intermittently, hardest on large models — the client
restarts it and retries the request once instead of letting the whole
app die. A second consecutive death raises EngineCrashed with a
human-actionable message.

Model downloads (pure-Python HF fetch) stay in THIS process: they are
crash-safe and need progress callbacks.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np

from core.config import Config
from core.engine import Engine, TranscriptionResult
from core.sttworker import read_frame, write_frame

log = logging.getLogger(__name__)

_LOAD_TIMEOUT_S = 600     # big model from a slow disk + warm-up
_TRANSCRIBE_TIMEOUT_S = 600
_CREATE_NO_WINDOW = 0x08000000


class EngineCrashed(RuntimeError):
    """The worker died twice in a row on the same request."""


def _worker_command() -> tuple[list[str], str | None]:
    """Command line + cwd to start the worker for this build flavor."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--stt-worker"], None
    root = Path(__file__).resolve().parents[1]
    return [sys.executable, "-X", "utf8", "-m", "core.sttworker"], str(root)


class IsolatedEngine:
    """Engine facade that proxies decode work to a worker process."""

    def __init__(self, config: Config | None = None,
                 overrides: dict | None = None):
        self.config = config or Config()
        self._overrides = overrides          # e.g. bench: {"model_size": ...}
        self._local = Engine(self.config)    # downloads/cache checks only
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._loaded = False
        self.actual_device: str | None = None    # after fallback, from worker
        self.actual_compute: str | None = None
        # What the worker was ASKED to load (model, device, compute) — the
        # shell compares against this to know when a restart is due.
        self.loaded_key: tuple[str, str, str] | None = None

    # -- passthrough (no native code involved) ---------------------------

    def is_model_cached(self) -> bool:
        self._sync_local_config()
        return self._local.is_model_cached()

    def ensure_model(self, progress_cb=None) -> None:
        self._sync_local_config()
        self._local.ensure_model(progress_cb=progress_cb)

    def _sync_local_config(self) -> None:
        if self._overrides:
            for key, value in self._overrides.items():
                if hasattr(self._local.config, key):
                    setattr(self._local.config, key, value)

    # -- worker lifecycle --------------------------------------------------

    def _spawn(self) -> None:
        import os

        cmd, cwd = _worker_command()
        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        # The worker waits on this PID and self-terminates when the app
        # dies — pipe EOF alone proved unreliable (orphaned ~1 GB workers).
        env = {**os.environ, "PARROTYPE_PARENT_PID": str(os.getpid())}
        kwargs["env"] = env
        try:
            from core.config import app_data_dir

            stderr = open(  # noqa: SIM115 — worker owns fd 2 right after start
                app_data_dir() / "worker.log", "ab",
            )
        except Exception:
            stderr = subprocess.DEVNULL
        self._proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
            **kwargs,
        )
        log.info("STT worker spawned (pid %s)", self._proc.pid)

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None
        self._loaded = False

    def abort(self) -> None:
        """Kill the worker immediately WITHOUT taking the lock.

        Used to supersede an in-flight model load when the user picks a
        different model: the blocked load request fails fast (its caller
        checks a generation counter and stays quiet), the lock frees, and
        the next load starts with the new config. Never blocks the GUI.
        """
        self._kill()

    def shutdown(self) -> None:
        """Graceful stop (app quit)."""
        with self._lock:
            if self._alive():
                try:
                    self._request({"cmd": "exit"}, timeout_s=3)
                except Exception:
                    pass
            self._kill()

    # -- framed request/response with a watchdog ---------------------------

    def _request(self, header: dict, payload: bytes = b"",
                 timeout_s: float = _TRANSCRIBE_TIMEOUT_S) -> dict:
        """Send one frame, read one frame. Raises ChildProcessError on death."""
        proc = self._proc
        assert proc is not None and proc.stdin and proc.stdout
        watchdog = threading.Timer(timeout_s, proc.kill)
        watchdog.daemon = True
        watchdog.start()
        try:
            write_frame(proc.stdin.fileno(), header, payload)
            proc.stdin.flush()
            response, _ = read_frame(proc.stdout.fileno())
            return response
        except (EOFError, OSError, ValueError) as exc:
            code = proc.poll()
            raise ChildProcessError(
                f"STT worker died (exit={code}, cmd={header.get('cmd')}): {exc}"
            ) from exc
        finally:
            watchdog.cancel()

    def _ensure_loaded(self) -> None:
        if not self._alive():
            self._kill()
            self._spawn()
            self._loaded = False
        if not self._loaded:
            response = self._request(
                {"cmd": "load", "overrides": self._overrides, "warm": True},
                timeout_s=_LOAD_TIMEOUT_S,
            )
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "model load failed"))
            self.actual_device = response.get("device")
            self.actual_compute = response.get("compute")
            self.loaded_key = (self.config.model_size, *self.config.resolve_device())
            self._loaded = True
            log.info(
                "Worker model ready: %s/%s load=%.1fs warm=%.1fs",
                response.get("device"), response.get("compute"),
                response.get("load_s", 0), response.get("warm_s", 0),
            )

    # -- Engine-compatible surface -----------------------------------------

    @property
    def model_loaded(self) -> bool:
        return self._loaded and self._alive()

    def load_model(self) -> None:
        with self._lock:
            self._ensure_loaded()

    def warm_up(self) -> float:
        # Warm-up runs inside the worker as part of load.
        self.load_model()
        return 0.0

    def unload_model(self) -> None:
        with self._lock:
            self._kill()

    def reload_postfilter(self) -> None:
        # Worker re-reads config from disk on its next load command; nudge
        # it now so dictionary/context edits apply to the next dictation.
        with self._lock:
            if self._alive() and self._loaded:
                self._loaded = False
                try:
                    self._ensure_loaded()
                except Exception:
                    log.exception("Worker config reload failed")
                    self._kill()

    def transcribe(self, audio) -> TranscriptionResult:  # noqa: ANN001
        """Transcribe a float32 numpy array or a WAV path. Crash-safe."""
        if isinstance(audio, np.ndarray):
            header: dict = {"cmd": "transcribe"}
            payload = np.ascontiguousarray(audio, dtype=np.float32).tobytes()
        else:
            header = {"cmd": "transcribe_path", "path": str(audio)}
            payload = b""

        last_error: Exception | None = None
        with self._lock:
            for attempt in (1, 2):
                try:
                    self._ensure_loaded()
                    response = self._request(header, payload)
                    if not response.get("ok"):
                        raise RuntimeError(response.get("error", "transcribe failed"))
                    return TranscriptionResult(
                        text=response["text"],
                        raw_text=response["raw_text"],
                        language=response["language"],
                        audio_seconds=response["audio_seconds"],
                        latency_seconds=response["latency_seconds"],
                        segments=list(response.get("segments", [])),
                    )
                except ChildProcessError as exc:
                    # Native crash in the decode: restart the worker; retry once.
                    last_error = exc
                    log.error("STT worker crashed (attempt %d/2): %s", attempt, exc)
                    self._kill()
        raise EngineCrashed(
            f"Speech engine crashed twice on this configuration "
            f"({self.config.model_size}). Try a smaller model or the GPU. "
            f"[{last_error}]"
        )

    def polish(self, text: str, language: str | None = None,
               deadline_s: float = 8.0) -> dict:
        """LLM cleanup in the worker. NEVER raises — a polish problem must
        not cost the user their dictation; worst case returns the text
        unchanged with fell_back=True."""
        fallback = {"text": text, "raw_text": text, "changed": False,
                    "fell_back": True, "reason": "unavailable"}
        try:
            with self._lock:
                self._ensure_loaded()
                response = self._request(
                    {"cmd": "polish", "text": text, "language": language,
                     "deadline_s": deadline_s},
                    timeout_s=deadline_s + 30,   # + model load headroom
                )
            if response.get("ok"):
                return response
            log.error("Polish failed: %s", response.get("error"))
            return {**fallback, "reason": str(response.get("error", ""))}
        except ChildProcessError as exc:
            # Native crash inside llama.cpp: recover the worker, keep raw.
            log.error("Worker crashed during polish: %s", exc)
            self._kill()
            return {**fallback, "reason": "crash"}
        except Exception as exc:
            log.exception("Polish request failed")
            return {**fallback, "reason": str(exc)}
