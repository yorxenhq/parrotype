"""PyInstaller entry point for the Parrotype tray application.

In a windowed (no-console) build the process has no standard streams:
sys.stdout / sys.stderr are None and OS-level fds 1/2 point nowhere.
Native libraries (ctranslate2 / OpenMP) write to those fds directly from
C code, which can kill the process without a traceback — this bit us on
the very first transcription of the packaged build. Route both streams
to a log file at the *fd* level before anything heavy is imported.
"""

import os
import sys

# ctranslate2 (Intel OpenMP / libiomp5md) and onnxruntime (the bundled
# Silero VAD) each run their own thread pool. Intel OpenMP threads
# SPIN-WAIT by default (KMP_BLOCKTIME=200ms) after a parallel region;
# those spinning threads race the onnxruntime VAD pool and intermittently
# access-violate on CPU inference in the packaged build. Make OpenMP
# threads sleep instead of spin, and allow the duplicate runtime. Must be
# set before ctranslate2/onnxruntime are imported (i.e. here, first).
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("KMP_BLOCKTIME", "0")
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

# STT worker mode: this same exe hosts the isolated decode process
# (core.sttclient spawns `Parrotype.exe --stt-worker`). Branch BEFORE the
# stdio redirect below — the worker's stdin/stdout ARE its IPC channel and
# it performs its own fd discipline (core.sttworker._steal_stdio).
if "--stt-worker" in sys.argv:
    from core.sttworker import main as _worker_main

    sys.exit(_worker_main())


def _stream_ok(stream) -> bool:
    if stream is None:
        return False
    try:
        stream.fileno()
        return True
    except Exception:
        return False


def _ensure_stdio() -> None:
    if _stream_ok(sys.stdout) and _stream_ok(sys.stderr):
        return
    try:
        appdata = os.path.join(os.environ.get("APPDATA", "."), "Parrotype")
        os.makedirs(appdata, exist_ok=True)
        target = open(
            os.path.join(appdata, "stdio.log"),
            "a",
            buffering=1,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        target = open(os.devnull, "w")  # noqa: SIM115
    fd = target.fileno()
    # dup2 creates/replaces fds 1 and 2 so C-level writes land in the file.
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    sys.stdout = target
    sys.stderr = target


_ensure_stdio()

import faulthandler  # noqa: E402

try:
    faulthandler.enable(file=sys.stderr)
except Exception:
    pass

from shells.tray.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
