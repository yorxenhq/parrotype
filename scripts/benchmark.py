"""Latency benchmark: transcribe a test WAV across model sizes and devices.

Prints a Markdown table (for README). Each cell = wall-clock transcription
time of the warm run (model loaded, second pass) on the test audio.

Run: python scripts/benchmark.py [wav_path]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import Config, Engine  # noqa: E402
from core.config import cuda_available  # noqa: E402

MODELS = ["tiny", "base", "small", "medium"]
GPU_EXTRA = ["large-v3-turbo", "large-v3"]


def bench(wav: str, model: str, device: str) -> tuple[float, str]:
    cfg = Config()
    cfg.model_size = model
    cfg.device = device
    cfg.compute_type = "auto"
    engine = Engine(cfg)
    engine.load_model()
    engine.transcribe(wav)          # warm-up (first pass includes graph init)
    result = engine.transcribe(wav)  # measured
    return result.latency_seconds, result.text


def main() -> None:
    wav = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "assets" / "latency_test.wav"
    )
    has_gpu = cuda_available()
    devices = ["cpu"] + (["cuda"] if has_gpu else [])
    print(f"Audio: {wav}")
    print(f"CUDA available: {has_gpu}\n")

    rows: list[tuple[str, dict[str, float]]] = []
    texts: dict[str, str] = {}
    for model in MODELS + (GPU_EXTRA if has_gpu else []):
        cells: dict[str, float] = {}
        for device in devices:
            if model in GPU_EXTRA and device == "cpu":
                continue  # too slow to be a realistic option; skip
            try:
                latency, text = bench(wav, model, device)
                cells[device] = latency
                texts[f"{model}@{device}"] = text
                print(f"  {model} @ {device}: {latency:.2f}s", file=sys.stderr)
            except Exception as exc:
                print(f"  {model} @ {device}: FAILED {exc}", file=sys.stderr)
        rows.append((model, cells))

    header = "| Model | " + " | ".join(
        ("CPU int8" if d == "cpu" else "GPU float16") for d in devices
    ) + " |"
    print("\n" + header)
    print("|" + "---|" * (len(devices) + 1))
    for model, cells in rows:
        line = f"| {model} |"
        for device in devices:
            value = cells.get(device)
            line += f" {value:.2f}s |" if value is not None else " — |"
        print(line)

    print("\nTranscripts (warm run):")
    for key, text in texts.items():
        print(f"  [{key}] {text}")


if __name__ == "__main__":
    main()
