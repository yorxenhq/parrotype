"""On-demand CUDA runtime for the packaged build.

The installer ships CPU-only (a bundled CUDA runtime would add gigabytes
for every user, GPU or not). When an NVIDIA device is present but the
runtime DLLs are absent, the app offers a one-time download: the pinned
NVIDIA wheels are fetched from PyPI, their DLLs extracted into
%APPDATA%/Parrotype/cuda/bin, and registered on the DLL search path.
ctranslate2 then loads them exactly as it would from pip wheels.

Versions are pinned to the set proven on the reference machine
(RTX 4050, ctranslate2 4.8.1); "latest" could silently break ABI.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from core.config import app_data_dir

log = logging.getLogger(__name__)

# Proven combination: ctranslate2 4.8.1 + cuBLAS 12 + cuDNN 9 (dev venv,
# GPU float16 measured 0.78s / 13.5s audio, zero crashes in every test).
PINNED_WHEELS: dict[str, str] = {
    "nvidia-cublas-cu12": "12.9.2.10",
    "nvidia-cudnn-cu12": "9.24.0.43",
    "nvidia-cuda-nvrtc-cu12": "12.9.86",   # cuDNN 9 graph engine needs NVRTC
}

_REQUIRED_DLLS = ("cublas64_12.dll", "cudnn64_9.dll")


def cuda_runtime_dir() -> Path:
    return app_data_dir() / "cuda" / "bin"


def cuda_runtime_present() -> bool:
    """True when the downloaded runtime is complete enough to try the GPU."""
    bin_dir = cuda_runtime_dir()
    return all((bin_dir / dll).exists() for dll in _REQUIRED_DLLS)


def register_runtime_dir() -> None:
    """Put the downloaded runtime on the DLL search path (idempotent).

    ctranslate2 resolves cuBLAS/cuDNN with a plain LoadLibrary, which
    ignores add_dll_directory dirs — PATH is needed as well (same trick
    as core.engine._register_cuda_dlls for pip wheels).
    """
    if sys.platform != "win32":
        return
    bin_dir = cuda_runtime_dir()
    if not bin_dir.is_dir():
        return
    path = os.environ.get("PATH", "")
    if str(bin_dir) not in path:
        os.environ["PATH"] = str(bin_dir) + os.pathsep + path
    try:
        os.add_dll_directory(str(bin_dir))
    except OSError as exc:
        log.debug("add_dll_directory(%s) failed: %s", bin_dir, exc)


def _wheel_url_and_size(package: str, version: str) -> tuple[str, int]:
    """Resolve the win_amd64 wheel URL + exact byte size from PyPI metadata."""
    api = f"https://pypi.org/pypi/{package}/{version}/json"
    with urllib.request.urlopen(api, timeout=30) as response:
        meta = json.load(response)
    for entry in meta.get("urls", []):
        name = entry.get("filename", "")
        if name.endswith(".whl") and "win_amd64" in name:
            return entry["url"], int(entry.get("size", 0))
    raise RuntimeError(f"no win_amd64 wheel on PyPI for {package}=={version}")


def download_total_bytes() -> int:
    """Exact download size of all pinned wheels (one PyPI query each)."""
    return sum(
        _wheel_url_and_size(pkg, ver)[1] for pkg, ver in PINNED_WHEELS.items()
    )


def install_cuda_runtime(progress_cb=None, cancel_check=None) -> Path:
    """Download the pinned wheels and extract their DLLs. Blocking.

    progress_cb(percent: int) covers the whole multi-wheel download by
    byte count. cancel_check() returning True aborts cleanly (partial
    temp files are discarded; the target dir is only touched at the end
    of each wheel, so an aborted install never leaves a half runtime
    that cuda_runtime_present() would misread — the REQUIRED dlls come
    from different wheels, both must land).
    """
    resolved = [
        (pkg, *_wheel_url_and_size(pkg, ver)) for pkg, ver in PINNED_WHEELS.items()
    ]
    total = sum(size for _, _, size in resolved) or 1
    done = 0
    bin_dir = cuda_runtime_dir()
    bin_dir.mkdir(parents=True, exist_ok=True)

    for package, url, _size in resolved:
        with tempfile.TemporaryDirectory(prefix="parrotype-cuda-") as tmp:
            wheel_path = Path(tmp) / f"{package}.whl"
            log.info("Downloading %s from %s", package, url)
            with urllib.request.urlopen(url, timeout=60) as response, \
                    open(wheel_path, "wb") as out:
                while True:
                    if cancel_check is not None and cancel_check():
                        raise InterruptedError("CUDA runtime download cancelled")
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress_cb is not None:
                        progress_cb(min(99, int(done * 100 / total)))
            with zipfile.ZipFile(wheel_path) as wheel:
                for info in wheel.infolist():
                    name = info.filename
                    if name.lower().endswith(".dll") and "/bin/" in name.replace("\\", "/"):
                        target = bin_dir / Path(name).name
                        with wheel.open(info) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        log.info("Extracted %s", target.name)

    if not cuda_runtime_present():
        raise RuntimeError("CUDA runtime incomplete after install")
    register_runtime_dir()
    _invalidate_probes()
    if progress_cb is not None:
        progress_cb(100)
    log.info("CUDA runtime installed into %s", bin_dir)
    return bin_dir


def remove_cuda_runtime() -> None:
    """Delete the downloaded runtime (settings escape hatch / disk space)."""
    root = app_data_dir() / "cuda"
    shutil.rmtree(root, ignore_errors=True)
    _invalidate_probes()


def _invalidate_probes() -> None:
    """The hardware probes are lru_cached; installed/removed runtime changes
    their answer within the same app run."""
    from core import config as _config

    _config.cuda_available.cache_clear()
    _config.cuda_usable.cache_clear()
