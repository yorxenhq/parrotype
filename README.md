# Parrotype

**You talk. The parrot types.**

Local voice dictation for Windows: press a hotkey, speak, release — your
words are typed into whatever window you're in.

**Everything runs on your machine — your voice never leaves it.**
No cloud, no account, no telemetry; the Whisper model runs locally.

Status: **1.0.0** — core + polished tray app + first-run
wizard + CLI, reliability package, RU/EN UI, PyInstaller build + Inno
Setup script. Live-microphone flows and the installed build still need a
human pass (see [What still needs a human check](#what-still-needs-a-human-check)).

## Languages

**Optimized for English, Russian, Spanish, German, French, Italian,
Portuguese, Polish, Ukrainian, Dutch, Turkish, Japanese, Korean and
Chinese** — each passed a measured recognition-quality gate on the
production engine (>= 80% content-keyword recall; methodology and per-
language results: `scripts/lang_gate.py`, `design/preview/lang-gate.md`).
Auto-detect covers the 90+ languages of the underlying Whisper model —
that part is a property of Whisper, not a Parrotype guarantee.
UI languages: Russian + English (follows the system, switchable).

## What's implemented (v1)

- **`core/`** — UI-independent engine: audio capture (sounddevice, 16 kHz
  mono) -> Silero VAD -> faster-whisper STT -> replacement dictionary
  post-filter. Importable as a library; CUDA with automatic CPU fallback.
- **`shells/tray/`** — PySide6 tray app:
  - global hotkeys: push-to-talk (hold `ctrl+alt`) and toggle
    (`ctrl+shift+space`), via an in-repo WH_KEYBOARD_LL hook
  - status overlay pill (bottom-center, never steals focus, click-through):
    live waveform + mono timer while listening, spinner while transcribing,
    flash-and-fade confirmation with text preview, persistent error state
    (click opens the log); Esc cancels a recording
  - paste into the active window: clipboard + Ctrl+V, previous clipboard
    text restored
  - tray menu: status/model, copy last dictation, pause, settings, history
  - settings window (sidebar): hotkeys / language (auto + 14 languages) / microphone /
    autostart / sound ticks · model + device + **latency test** · replacement
    dictionary ("клод" -> "Claude") · local history (last 50, can be
    disabled) · about
- **`shells/cli/`** — `python -m shells.cli audio.wav` or `--mic --seconds 10`
  -> text to stdout.
- Languages: auto-detect + the 14 gate-passed languages listed above. All
  processing local; history and config live in `%APPDATA%\Parrotype`.

Not in v1 (by spec): installer + first-run wizard (v1.5), HTTP microservice
shell (reserved), TTS direction (interface reserved), cloud anything (never).

## Run

```powershell
git clone https://github.com/yorxenhq/parrotype && cd parrotype
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
# optional, GPU (NVIDIA, CUDA 12): .venv\Scripts\pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
.venv\Scripts\python -m shells.tray      # tray app
.venv\Scripts\python -m shells.cli tests\data\test_en.wav --verbose   # CLI
```

First transcription downloads the model (~75 MB tiny … ~3 GB large-v3);
the pill and the first-run wizard show download progress.

## Packaged build (v1.5)

```powershell
.venv\Scripts\python -m PyInstaller packaging\parrotype.spec --noconfirm   # -> dist\Parrotype\
# installer (requires Inno Setup 6): ISCC.exe packaging\installer.iss     # -> dist\ParrotypeSetup.exe
```

The packaged build is CPU-only (NVIDIA CUDA runtimes are excluded to keep
the bundle sane); GPU users run from source. Model weights download on
first run through the wizard.

## Latency (measured)

Reference machine: RTX 4050 Laptop 6GB, 32GB RAM, Python 3.13.
Warm-run transcription time for a 13.5s English WAV with the production
decode parameters — anti-hallucination temperature cascade + tuned VAD
(see `scripts/benchmark.py`; first pass per model excluded as warm-up):

| Model | CPU int8 | GPU float16 |
|---|---|---|
| tiny | 0.50s | 0.25s |
| base | 0.84s | 0.30s |
| small | 2.44s | 0.48s |
| medium | 6.81s | 0.94s |
| large-v3-turbo | — | 0.78s |
| large-v3 | — | 6.53s* |

\* large-v3 on this 6GB GPU triggers the fallback decode cascade and is
much slower under the production parameters than in a bare greedy run.

**Default:** `large-v3-turbo` when CUDA is available (best quality per
second, 0.78s), `small` on CPU-only machines. Pick differently in
Settings -> Модель -> Тест латентности.

## Testing

Machine-verified (`pytest tests`, `scripts/selftest_*.py`):

- 42 unit/integration tests: config, history, post-filter dictionary,
  reliability guards, recognition quality, and end-to-end STT on synthesized
  English speech (keywords + dictionary replacement verified on real model
  output)
- tray app boots headless: tray icon, menu, all overlay states, focus and
  click-through flags (18 checks)
- global hotkey plumbing with injected input through the real OS hook:
  PTT press/release, toggle, Esc-cancel, pause gate (8 checks)
- paste path against a live Notepad: text lands in the window, clipboard
  restored (verified via WM_GETTEXT, retry-hardened against focus stealing)
- dependency license audit — see `LICENSES.md`

### What still needs a human check

- dictation from a **real microphone** (test audio was synthesized TTS)
- **Russian and mixed RU+EN speech quality** — the build machine had no
  Russian TTS voice, so only English was machine-tested end-to-end
- hotkeys while a fullscreen/elevated app is focused (browser, VS Code,
  Telegram were not human-verified)
- subjective latency feel and overlay legibility on multi-monitor setups
- autostart registry entry across a real reboot

## Repo map

```
core/          engine, audio capture, config, history, post-filter
shells/tray/   PySide6 app: overlay, tray, settings, hotkeys, paste
shells/cli/    stdout transcription
assets/        logo.svg + logo-small.svg + appicon.svg (canonical "bar-parrot"
               mark: full / no-eye tray variant / plaque icon), generated
               app.ico + png, test WAV
scripts/       benchmark + self-tests (tray / hotkey / paste) + TTS fixtures
tests/         pytest suite
DECISIONS.md   non-obvious calls made during the build
LICENSES.md    dependency license audit
```

License: MIT (dependencies audited in `LICENSES.md`).
