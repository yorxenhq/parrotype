# Dependency license audit

Audited 2026-07-16 with `pip-licenses` against the pinned environment
(Python 3.13, `requirements.txt` + transitive dependencies).
Goal: everything distribution-safe (MIT / Apache / BSD / LGPL-dynamic).

## Verdict

**OK for distribution.** Notes:

- **PySide6 / shiboken6 — LGPL-3.0.** Used via dynamic linking (standard
  pip wheels, no static linking, no source modification), which satisfies
  LGPL for a closed or open distribution. If the app is ever packaged with
  PyInstaller, the Qt DLLs stay separate files — still dynamic linking.
- **NVIDIA cuBLAS / cuDNN / nvRTC — proprietary redistributables.** Only
  needed for GPU inference. NVIDIA's EULA permits redistribution of the
  runtime libraries with applications, but the clean option for a public
  installer is to ship CPU-only by default and fetch CUDA wheels as an
  optional post-install step. Not shipped in the repo.
- **Whisper model weights — MIT** (OpenAI Whisper release; served through
  Hugging Face by the faster-whisper project). Downloaded at first run,
  not stored in the repo.
- Everything else is MIT / Apache-2.0 / BSD / MPL-2.0 (file-level copyleft,
  unmodified use is fine) / PSF-2.0.

## Direct dependencies (runtime)

| Package | Version | License |
|---|---|---|
| faster-whisper | 1.2.1 | MIT |
| ctranslate2 | 4.8.1 | MIT |
| sounddevice | 0.5.5 | MIT |
| numpy | 2.5.1 | BSD-3-Clause (and vendored: 0BSD/MIT/Zlib/CC0) |
| PySide6 (+Essentials/Addons, shiboken6) | 6.11.1 | LGPL-3.0-only (dynamic) |
| pyperclip | 1.11.0 | BSD |
| pycaw (+comtypes) | 20251023 | MIT |

Optional (GPU only): nvidia-cublas-cu12, nvidia-cudnn-cu12,
nvidia-cuda-nvrtc-cu12 — proprietary NVIDIA redistributables.

## Transitive dependencies

| Package | License |
|---|---|
| av | BSD-3-Clause |
| huggingface_hub, tokenizers, hf-xet, flatbuffers | Apache-2.0 |
| onnxruntime | MIT |
| protobuf | BSD-3-Clause |
| httpx, httpcore, h11, anyio, idna | BSD / MIT |
| filelock, PyYAML, pluggy | MIT |
| cffi | MIT-0 |
| pycparser | BSD-3-Clause |
| tqdm | MPL-2.0 AND MIT |
| certifi | MPL-2.0 |
| typing_extensions | PSF-2.0 |
| packaging | Apache-2.0 OR BSD-2-Clause |
| click, colorama, fsspec, Pygments | BSD |

## Dev-only (not distributed)

pytest (MIT), pip-licenses (MIT), Pillow (MIT-CMU — used once to build the
.ico at development time; not a runtime dependency).

Removed during development: `keyboard` (MIT) — replaced by an in-repo
ctypes implementation (`shells/tray/wininput.py`), see DECISIONS.md.
