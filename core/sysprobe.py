"""Lightweight hardware summary for the model picker / wizard.

One human line: what this machine has, so the model recommendation is
visibly grounded ("подобрано под эту машину", not a generic default).
All probes are best-effort and cheap; failures degrade to omission.
"""

from __future__ import annotations

import ctypes
import functools
import logging
import os
import subprocess
import sys

log = logging.getLogger(__name__)

_CREATE_NO_WINDOW = 0x08000000


@functools.lru_cache(maxsize=1)
def cpu_label() -> str:
    """Marketing CPU name from the registry (e.g. 'AMD Ryzen AI 9 365')."""
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as key:
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        return " ".join(str(name).split())
    except OSError:
        return ""


@functools.lru_cache(maxsize=1)
def ram_gb() -> int:
    """Physical RAM, GiB (GlobalMemoryStatusEx)."""
    if sys.platform != "win32":
        return 0

    class _MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_uint32),
            ("dwMemoryLoad", ctypes.c_uint32),
            ("ullTotalPhys", ctypes.c_uint64),
            ("ullAvailPhys", ctypes.c_uint64),
            ("ullTotalPageFile", ctypes.c_uint64),
            ("ullAvailPageFile", ctypes.c_uint64),
            ("ullTotalVirtual", ctypes.c_uint64),
            ("ullAvailVirtual", ctypes.c_uint64),
            ("ullAvailExtendedVirtual", ctypes.c_uint64),
        ]

    status = _MEMORYSTATUSEX(dwLength=ctypes.sizeof(_MEMORYSTATUSEX))
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return 0
    return round(status.ullTotalPhys / (1 << 30))


@functools.lru_cache(maxsize=1)
def gpu_label() -> str:
    """NVIDIA GPU name via nvidia-smi ('' when absent/unreadable)."""
    if sys.platform != "win32":
        return ""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().splitlines()[0].strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def summary_line() -> str:
    """'AMD Ryzen 9 · 32 GB RAM · NVIDIA GeForce RTX 4050' (parts optional)."""
    parts = []
    cpu = cpu_label()
    if cpu:
        parts.append(cpu)
    cores = os.cpu_count() or 0
    ram = ram_gb()
    if ram:
        parts.append(f"{ram} GB RAM")
    elif cores:
        parts.append(f"{cores} threads")
    gpu = gpu_label()
    if gpu:
        parts.append(gpu)
    return " · ".join(parts)
