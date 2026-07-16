# PyInstaller spec: onedir build of the Parrotype tray app.
# Build:  .venv\Scripts\python -m PyInstaller packaging\parrotype.spec --noconfirm
# Output: dist/Parrotype/Parrotype.exe
#
# Notes:
# - Model weights are NOT bundled (downloaded on first run with progress).
# - NVIDIA CUDA runtime wheels are excluded: the packaged build runs on CPU
#   everywhere; GPU users run from source for now (documented in README).

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent

# faster-whisper ships its VAD model (silero_vad_*.onnx) as package data;
# without it the very first transcription of the packaged app fails.
_fw_assets = collect_data_files("faster_whisper", subdir="assets")

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "assets" / "logo.svg"), "assets"),
        (str(ROOT / "assets" / "logo-small.svg"), "assets"),
        (str(ROOT / "assets" / "appicon.svg"), "assets"),
        (str(ROOT / "assets" / "app.ico"), "assets"),
        (str(ROOT / "assets" / "latency_test.wav"), "assets"),
        (str(ROOT / "assets" / "fonts"), "assets/fonts"),
    ] + _fw_assets,
    hiddenimports=[
        "shells.tray.app",
        "sounddevice",
        "pycaw", "pycaw.pycaw", "comtypes.stream",
    ],
    excludes=[
        "nvidia", "nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc",
        "tests", "pytest", "PIL", "pyinstaller", "edge_tts",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore",
        "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="Parrotype",
    icon=str(ROOT / "assets" / "app.ico"),
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Parrotype",
)
