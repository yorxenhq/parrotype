# Design decisions

## D19. Finishing phase package (2026-07-16)
- **Packaged build is CPU-only**: NVIDIA CUDA runtime wheels (~800 MB,
  proprietary) are excluded from the PyInstaller bundle; GPU acceleration
  = run from source. Keeps the installer sane and the license story clean.
- **Language gate before language claims**: a language is listed as
  supported only after passing scripts/lang_gate.py (>= 80% content-
  keyword recall on the production engine; test speech synthesized with
  edge-tts — a dev-time tool, GPL-3.0, never shipped). All 14 candidates
  passed (min: de 83%) -> recognition combo + README list.
- **UI languages stay RU/EN in this pass.** The gate measures speech
  recognition, not translation quality; shipping machine-drafted UI
  strings in 12 more languages without a native review would undercut
  the product bar. Open item.
- **Screenshots policy**: all previews are QWidget.grab renders with
  WA_DontShowOnScreen (real widgets, real QSS, nothing flashes on the
  user's desktop); collages 1600px wide with Latin captions.

# v1 decisions

Contentious or non-obvious calls made during the autonomous v1 build,
resolved in favour of simplicity. Dated 2026-07-16 unless noted.

## D1. VAD = faster-whisper's built-in Silero filter
The spec pipeline is capture -> VAD -> STT. Recording boundaries in v1 are
explicit (push-to-talk hold / toggle press), so streaming endpointing is not
needed; Silero VAD runs as `vad_filter=True` inside faster-whisper (bundled
ONNX model) to strip silence/noise before decoding. No separate torch/silero
dependency, same model family the spec asks for.

## D2. Replaced the `keyboard` package with an in-repo ctypes module
`keyboard` 0.13.5 (unmaintained since 2020) silently receives zero events
from its WH_KEYBOARD_LL hook on this Python 3.13 / Win11 machine — verified
by injecting keys while a raw ctypes hook in the same process received them
fine. `shells/tray/wininput.py` now owns the hook (hotkeys) and SendInput
(Ctrl+V injection). Fewer dependencies, and hotkey detection is testable by
key injection.

## D3. Both hotkeys active simultaneously; toggle default made disjoint
Spec sketch shows a single "mode" selector. Implemented instead: PTT combo
(hold) and toggle combo (press) are both always bound — no mode switch
needed, both behaviours just work. Toggle default is `ctrl+shift+space`
(not `ctrl+alt+space`) so it is not a superset of the PTT default
(`ctrl+alt`), which would fire PTT first while pressing the toggle.

## D4. Hotkey capture UI = validated text field, not key-capture widget
Qt's `QKeySequenceEdit` cannot capture modifier-only combos like the PTT
default `ctrl+alt`. v1 uses a plain text field with live validation
(red border on unknown keys). A capture widget can come with the v1.5
first-run wizard.

## D5. Default model chosen by measurement, per hardware class
Benchmark on the reference machine (RTX 4050 6GB / 32GB RAM, 13.5s WAV):
GPU medium = 0.93s, GPU small = 0.44s, CPU small = 2.28s, CPU medium = 6.67s.
First-run default: **medium on CUDA** (best quality under 1s), **small on
CPU** (medium is too slow at ~7s). Stored in config on first run; user can
change it and re-measure via "Тест латентности".

## D6. First-run wizard deferred to v1.5
Spec §4 lists the wizard under v1.5; §3.5 describes it as "the face of v1.5
for the second user". v1 ships tray + settings only.

## D7. HTTP microservice shell not built in v1
Spec §3 marks it optional ("можно флагом, не обязателен") and §8 reserves
`POST /v1/transcribe` + `POST /v1/speak` (501). The core engine is the
integration point; the HTTP wrapper is an evening's work when a consumer
exists. Nothing in the core blocks it (engine is UI-free and importable).

## D8. speak() reserved, not implemented
Per instructions: the engine docstring documents the reserved TTS direction;
no dead code, no stub method. `Engine` is the single entry point a future
`speak(text)` would be added to.

## D9. Paste = clipboard + Ctrl+V with restore, text-only
Clipboard restore preserves plain text only (v1 limitation — images or
rich content on the clipboard before dictation are not restored).
`RESTORE_DELAY_S = 0.6s` between Ctrl+V and restore: measured on Win11
Notepad; shorter delays raced the target app's paste handling.

## D10. History delete index contract
`History.remove(i)` takes the index in newest-first order (what the UI
shows), not storage order.

## D18. New canonical mark: "bar-parrot" clean baseline (2026-07-16)
The owner reviewed mark directions and approved the clean baseline: three
waveform bars, the third rising into a round head with a dot eye — the
recognition wave IS the bird. Beaked/crested variants were rejected.
Files: `assets/logo.svg` (with eye, >= 48px / About / brand),
`assets/logo-small.svg` (no eye, tray 16-32px — the eye turns to noise at
tray sizes), `assets/appicon.svg` (mark in a plaque, exe/installer icon;
`app.ico` uses the small variant inside the plaque for its 16/32 frames).
Canonical geometry is never edited downstream (kit embeds it verbatim).
Supersedes the parrot-profile mark from the v1 build (D11 mechanism —
runtime SVG rendering — unchanged).

## D11. Tray/status icons rendered from the canonical SVG at runtime
`assets/logo.svg` is the approved mark; `shells/tray/icons.py` renders it
via QtSvg with state variants (16px simplified outline, red recording
badge, grey paused) — no hand-maintained PNG set. `assets/app.ico`
(16/32/48/256) is generated by `assets/generate_icon.py` for the exe/installer.

## D13. Insert path: unicode typing primary, hardened clipboard fallback (2026-07-16, live-session iteration)
The clipboard+Ctrl+V insert lost a dictation in live use (paste failed,
restore already ran) and raced the user's own copies. New design:
- **Primary: SendInput KEYEVENTF_UNICODE typing** (layout-independent,
  clipboard untouched) for texts <= 1000 chars; chunked with focus-abort
  support.
- **Fallback (long texts): clipboard + Ctrl+V**, hardened: waits for
  physical modifier release (GetAsyncKeyState, 2s timeout) before
  injecting; restore-delay 1.0s; restores the previous clipboard ONLY if
  the clipboard still contains our text.
- **No-loss guarantee:** any failure parks the recognized text on the
  clipboard and the pill says to press Ctrl+V; history is written before
  the insert attempt.
- `insert_method` config ("auto" | "clipboard") — measured on the build
  machine: a classic Win32 EDIT control accepts typed input 6/6 clean
  (per-char AND batched), while Win11 Notepad's async RichEditD2DPT
  garbled fast typed streams in repeated runs; real-world targets need a
  live check, and the setting is the escape hatch.

## D14. Hotkeys muted while settings dialog is open
AltGr on some layouts equals Ctrl+Alt — typing in the dictionary table
was starting PTT recordings. The tray app pauses the hotkey manager
while the settings dialog is visible (user-initiated pause is tracked
separately and survives the settings cycle).

## D15. Anti-hallucination decode set + VAD tail trimming (2026-07-16, iteration 2)
Live dictation produced a hallucinated tail (quiet mumble at the end of a
recording decoded into gibberish words). transcribe() now runs with an
explicit anti-hallucination set: condition_on_previous_text=False,
temperature cascade starting at 0.0, no_speech_threshold=0.6,
log_prob_threshold=-1.0, compression_ratio_threshold=2.4, and Silero VAD
tuned to cut quiet trailing audio (threshold 0.5, min_silence 500ms,
speech_pad 200ms, min_speech 250ms). Regression test: speech + 2s of quiet
noise must not gain words (tests/test_recognition_quality.py).

## D16. Recognition seed (initial_prompt) from the dictionary + user context
The right-hand sides of the replacement dictionary (the exact terms the
user dictates) are joined into whisper's initial_prompt, plus an optional
free-form "Контекст распознавания" field (settings -> Модель). Measured
effect: "Cloud Flair" -> "Cloudflare" on the tiny model with the term
seeded. Empty dictionary + empty context = no prompt (previous behavior).

## D17. GPU default model = large-v3-turbo (measured)
CUDA benchmark on the 13.5s test WAV (warm run, current decode params):
large-v3-turbo 0.78s vs medium 0.93s vs large-v3 5.7s. Turbo is under the
1.5s bar with the best quality per second -> first-run GPU default.
Caveat (documented for the live check): on the synthetic monotone test
voice turbo omitted punctuation when no initial_prompt was set; with any
seed present the punctuation returned. If it recurs on live speech with an
empty dictionary — add terms/context, or switch the model to medium.

## D12. Test audio is synthesized (SAPI), Russian voice unavailable
The build machine has only English SAPI voices (David/Zira/Mark) — no
Russian TTS installed, so the RU and RU+EN-mix acceptance cases could not
be machine-verified. English end-to-end tests pass; RU quality needs a
human check (see README).

## D-brand-2: logo usage — eye version is premium (2026-07-16)

The full mark (with the dot eye) is the premium form and MUST be used
wherever the mark is seen at a readable size: app UI (incl. the settings
sidebar footer), the website (nav + hero + og), README, and all
publications. It is a vector on the web, so the eye reads at any size.

The solid variant (no eye, logo-small.svg) is ONLY for the tray and
micro state-icons at 16-32px, where the eye becomes mud and the icon's
job is to signal state by colour, not to render the mark faithfully.
app.ico follows this: 16/32 frames use the solid variant inside the
tile, 48/256 use the full mark.

Sidebar footer mark: full mark recoloured to a quiet grey (#6B6B76),
eye punched to the panel colour, 45% opacity — a signature, not a logo.
Owner picked this over mint (competed with the accent, which must mean
"active/ready", not decorate chrome).

## D13. Root cause of the "random c0000005 on transcribe" — comtypes GC, not the decoder (2026-07-17)

The packaged-build access violations blamed on ctranslate2's CPU int8
kernels (D-greedy fix, beam=1/temp=0) were actually pycaw/comtypes:
COM pointers created on short-lived threads (startup self-check,
recording start) were RELEASED later by Python's garbage collector on a
foreign thread, after the creating thread's COM apartment was gone.
Big models made it frequent purely by allocating more (GC ran more
often inside the crash window) — hence "crashes on large-v3-turbo,
fine on small". Baseline stress before the fix: 5/12 packaged runs
died with the comtypes trace; the isolated decode worker crashed 0/12
times, exonerating the decoder.

Fix: every pycaw call runs on ONE long-lived COM worker thread and
gc.collect() runs there after each call (shells/tray/micguard.py).
Faulthandler traces made the culprit visible — keep faulthandler on.

## D14. Decode isolation + worker lifetime (2026-07-17)

Transcription runs in a separate worker process (core/sttworker.py,
client core/sttclient.py, `Parrotype.exe --stt-worker`): any residual
native crash kills the worker, the client restarts it and retries once,
the app never dies. A second consecutive death surfaces an honest
"unstable on this machine" (stored in config.bench_results, shown on
the model card). Worker self-terminates via a parent-PID watchdog —
pipe EOF alone left orphaned ~1 GB workers after parent crashes.

## D15-gpu. CUDA runtime on demand, installer stays CPU-only (2026-07-17)

NVIDIA present + runtime absent -> one-click download of pinned wheels
(cublas 12.9.2.10 / cudnn 9.24.0.43 / nvrtc 12.9.86, 1.37 GB by PyPI
metadata) into %APPDATA%/Parrotype/cuda/bin (core/cudasetup.py). Sizes
shown to the user are queried from PyPI, not hardcoded. Model picker
re-ranks for GPU after install; speed numbers in the picker switch to
real per-machine measurements once the latency test runs
(config.bench_results), never invented ones.

## D16. Polish layer: Qwen3-1.7B + двусторонний guard (2026-07-17)

Локальная LLM-полировка транскрипта: убирает филлеры, склеивает самоисправления, расставляет
пунктуацию, применяет словарь пользователя. Архитектура:
- Модель: Qwen3-1.7B Q4_K_M (unsloth GGUF, ~1.1 GB, Apache 2.0) через
  llama-cpp-python, /no_think. Выбрана A/B-прогоном на реальных
  замусоренных RU+EN диктовках: 8/8 чисто (Vikhr-Qwen-2.5-1.5B — 2/8,
  болтливый: исполняет императивы из текста вместо чистки).
- Промпт: текст подаётся как ДАННЫЕ в конверте «Диктовка: …», не как
  реплика (иначе модель выполняет «сделай рефакторинг» буквально);
  два языковых трека (RU/EN) — выбирает язык, определённый whisper.
- Guard (полировка никогда не хуже сырца): добавленное содержательное
  слово не из сырца/словаря -> откат; УДАЛЕНИЕ содержательных слов
  разрешено только при маркере самоисправления в сырце («нет»,
  «вернее», "wait"…) и не более половины; кредиты на цифровую
  нормализацию («три»->«3») и словарные замены («клауд код»->
  «Claude Code»). Модель однажды молча выкинула целое предложение —
  guard v1 ловил только добавления, v2 ловит и потери.
- Исполнение: в том же изолированном воркере (краш llama.cpp = рестарт
  воркера, не приложения); стриминг с wall-clock дедлайном 8 с;
  сырец каждой полированной диктовки сохраняется в history.raw.
- Выключена по умолчанию; включение в настройках качает модель один раз.
