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

# ctranslate2 and onnxruntime each bundle an OpenMP runtime; duplicate
# runtimes in one frozen process can intermittently access-violate on
# CPU decode. The standard mitigation, set before either library loads:
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


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
