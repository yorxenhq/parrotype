"""Self-test for the isolated STT worker (core.sttclient / core.sttworker).

1. transcribe a WAV through the worker process — result must be non-empty;
2. kill the worker mid-session — the next transcribe must transparently
   restart it and still return a result (the crash-recovery contract);
3. force a double-death — EngineCrashed must surface, the app-side
   contract for "this configuration is unstable on this machine".

Run: python scripts/selftest_worker.py [wav_path]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.sttclient import EngineCrashed, IsolatedEngine  # noqa: E402


def main() -> int:
    wav = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "assets" / "latency_test.wav"
    )
    cfg = Config.load()
    cfg.model_size = "small"
    cfg.device = "cpu"
    cfg.compute_type = "int8"
    engine = IsolatedEngine(cfg)

    print("1) plain transcribe through worker ...")
    t0 = time.perf_counter()
    result = engine.transcribe(wav)
    assert result.text, "empty transcription"
    print(f"   OK {time.perf_counter() - t0:.1f}s: {result.text[:80]!r}")

    print("2) kill worker, next transcribe must auto-recover ...")
    assert engine._proc is not None
    engine._proc.kill()
    time.sleep(0.3)
    result = engine.transcribe(wav)
    assert result.text, "empty transcription after recovery"
    print(f"   OK recovered: {result.text[:80]!r}")

    print("3) double-death must raise EngineCrashed ...")

    class _AlwaysDead(IsolatedEngine):
        def _ensure_loaded(self) -> None:
            super()._ensure_loaded()
            self._proc.kill()          # die right before every request
            time.sleep(0.2)

    dead = _AlwaysDead(cfg)
    try:
        dead.transcribe(wav)
    except EngineCrashed as exc:
        print(f"   OK EngineCrashed: {exc}")
    else:
        print("   FAIL: no EngineCrashed raised")
        return 1

    engine.shutdown()
    dead.shutdown()
    print("ALL WORKER TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
