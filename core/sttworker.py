"""STT worker process: runs the whisper decode in its own process.

Why a separate process: ctranslate2's CPU int8 kernels intermittently
access-violate (c0000005) inside the packaged build — worse on large
models — and a native crash cannot be caught in-process. Isolating the
decode means a crash kills THIS process only; the client restarts it and
retries, so the app never dies mid-dictation on any machine.

Protocol (binary, over the process's original stdin/stdout):
    frame  = <u32 little-endian: header length> <header: UTF-8 JSON>
             <payload: header["payload"] raw bytes (optional)>
    request headers:
      {"cmd": "load", "overrides": {...}|null, "warm": bool}
      {"cmd": "transcribe", "n": <float32 samples in payload>}
      {"cmd": "transcribe_path", "path": "<wav path>"}
      {"cmd": "exit"}
    responses mirror the frame format; {"ok": true, ...} or
    {"ok": false, "error": "..."}.

fd discipline: the IPC pipes are dup()ed away from fds 0/1 first, then
fds 0/1/2 are pointed at a log file — native libraries write to fds 1/2
directly from C and would otherwise corrupt the protocol stream.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import sys
import time

log = logging.getLogger(__name__)

_HDR = struct.Struct("<I")


def _read_exact(fd: int, n: int) -> bytes:
    chunks = []
    while n > 0:
        chunk = os.read(fd, min(n, 1 << 20))
        if not chunk:
            raise EOFError("IPC pipe closed")
        chunks.append(chunk)
        n -= len(chunk)
    return b"".join(chunks)


def read_frame(fd: int) -> tuple[dict, bytes]:
    header_len = _HDR.unpack(_read_exact(fd, _HDR.size))[0]
    header = json.loads(_read_exact(fd, header_len).decode("utf-8"))
    payload = _read_exact(fd, int(header.get("payload", 0)))
    return header, payload


def write_frame(fd: int, header: dict, payload: bytes = b"") -> None:
    if payload:
        header = {**header, "payload": len(payload)}
    raw = json.dumps(header, ensure_ascii=False).encode("utf-8")
    os.write(fd, _HDR.pack(len(raw)) + raw + payload)


def _steal_stdio() -> tuple[int, int]:
    """Dup the IPC pipes off fds 0/1, then point 0/1/2 at the worker log."""
    import msvcrt

    ipc_in = os.dup(0)
    ipc_out = os.dup(1)
    if sys.platform == "win32":
        msvcrt.setmode(ipc_in, os.O_BINARY)
        msvcrt.setmode(ipc_out, os.O_BINARY)

    from core.config import app_data_dir

    try:
        target = open(app_data_dir() / "worker.log", "a",
                      buffering=1, encoding="utf-8", errors="replace")
    except Exception:
        target = open(os.devnull, "w")  # noqa: SIM115
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)
    os.dup2(target.fileno(), 1)
    os.dup2(target.fileno(), 2)
    sys.stdin = open(os.devnull, encoding="utf-8")
    sys.stdout = target
    sys.stderr = target
    return ipc_in, ipc_out


def _handle_load(engine, header: dict) -> dict:  # noqa: ANN001
    from core.config import Config

    config = Config.load()
    for key, value in (header.get("overrides") or {}).items():
        if hasattr(config, key):
            setattr(config, key, value)
    engine.config = config
    engine.reload_postfilter()
    t0 = time.perf_counter()
    engine.load_model()
    load_s = time.perf_counter() - t0
    warm_s = engine.warm_up() if header.get("warm", True) else 0.0
    device, compute = config.resolve_device()
    return {
        "ok": True, "device": device, "compute": compute,
        "load_s": round(load_s, 3), "warm_s": round(warm_s, 3),
    }


def _result_header(result) -> dict:  # noqa: ANN001
    return {
        "ok": True,
        "text": result.text,
        "raw_text": result.raw_text,
        "language": result.language,
        "audio_seconds": result.audio_seconds,
        "latency_seconds": result.latency_seconds,
        "segments": result.segments,
    }


def _watch_parent() -> None:
    """Self-terminate the moment the parent app dies.

    The pipe-EOF path is not fully reliable on Windows (orphaned workers
    holding ~1 GB of model each were observed after parent crashes), so a
    dedicated thread waits on the parent process handle and hard-exits.
    """
    parent_pid = os.environ.get("PARROTYPE_PARENT_PID", "")
    if not parent_pid.isdigit() or sys.platform != "win32":
        return
    import ctypes
    import threading

    SYNCHRONIZE = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(parent_pid))
    if not handle:
        log.warning("Cannot open parent process %s; watchdog disabled", parent_pid)
        return

    def waiter() -> None:
        ctypes.windll.kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
        log.info("Parent %s exited; worker self-terminating", parent_pid)
        os._exit(0)

    threading.Thread(target=waiter, daemon=True, name="parent-watchdog").start()


def main() -> int:
    ipc_in, ipc_out = _steal_stdio()
    _watch_parent()

    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    import faulthandler

    faulthandler.enable(file=sys.stderr)
    log.info("STT worker started (pid %s)", os.getpid())

    import numpy as np

    from core.engine import Engine

    engine = Engine()

    while True:
        try:
            header, payload = read_frame(ipc_in)
        except EOFError:
            log.info("IPC closed; worker exiting")
            return 0
        cmd = header.get("cmd", "")
        try:
            if cmd == "exit":
                write_frame(ipc_out, {"ok": True})
                return 0
            elif cmd == "load":
                write_frame(ipc_out, _handle_load(engine, header))
            elif cmd == "transcribe":
                audio = np.frombuffer(payload, dtype=np.float32)
                write_frame(ipc_out, _result_header(engine.transcribe(audio)))
            elif cmd == "transcribe_path":
                write_frame(
                    ipc_out, _result_header(engine.transcribe(header["path"]))
                )
            else:
                write_frame(ipc_out, {"ok": False, "error": f"unknown cmd {cmd!r}"})
        except Exception as exc:
            log.exception("Worker command %r failed", cmd)
            write_frame(ipc_out, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    sys.exit(main())
