"""CLI: transcribe a WAV file or a timed microphone recording to stdout.

Usage:
    python -m shells.cli audio.wav
    python -m shells.cli --mic --seconds 10
    python -m shells.cli audio.wav --model small --language ru --device cpu
"""

from __future__ import annotations

import argparse
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="parrotype-cli", description="Local speech-to-text (faster-whisper)."
    )
    parser.add_argument("wav", nargs="?", help="path to a WAV file")
    parser.add_argument("--mic", action="store_true", help="record from microphone")
    parser.add_argument(
        "--seconds", type=float, default=10.0, help="mic recording length (default 10)"
    )
    parser.add_argument(
        "--model", help="model size (tiny/base/small/medium/large-v3-turbo/large-v3)"
    )
    parser.add_argument("--language", help="auto or a whisper language code (ru, en, …)")
    parser.add_argument("--device", help="cuda / cpu / auto")
    parser.add_argument(
        "--raw", action="store_true", help="skip the replacement dictionary"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print timing info to stderr"
    )
    args = parser.parse_args(argv)

    if not args.wav and not args.mic:
        parser.error("give a WAV file or --mic")

    from core import Config, Engine

    config = Config.load()
    if args.model:
        config.model_size = args.model
    if args.language:
        config.language = args.language
    if args.device:
        config.device = args.device
        config.compute_type = "auto"

    engine = Engine(config)

    if args.mic:
        from core import Recorder

        recorder = Recorder(
            sample_rate=config.sample_rate, device=config.input_device
        )
        print(f"Recording {args.seconds:.0f}s…", file=sys.stderr)
        recorder.start()
        time.sleep(args.seconds)
        audio = recorder.stop()
        result = engine.transcribe(audio)
    else:
        result = engine.transcribe(args.wav)

    print(result.raw_text if args.raw else result.text)
    if args.verbose:
        device, compute = config.resolve_device()
        print(
            f"[{config.model_size} @ {device}/{compute}] "
            f"lang={result.language} audio={result.audio_seconds:.1f}s "
            f"latency={result.latency_seconds:.2f}s",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
