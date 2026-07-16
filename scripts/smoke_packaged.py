"""Packaged-build smoke test: copy dist to a clean temp dir, run, verify.

Checks (no desktop interaction):
  1. dist copies and starts from a clean directory (no repo, no venv)
  2. the process survives startup (no crash within the wait window)
  3. the log shows the model loaded and no tracebacks
Config is pre-seeded (first_run_done, tiny/cpu) so no wizard pops up
and no GPU is required.

Run: python scripts/smoke_packaged.py   -> PASS/FAIL, exit 0/1
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "Parrotype"
WAIT_S = 45


def main() -> int:
    if not (DIST / "Parrotype.exe").exists():
        print("FAIL: dist/Parrotype/Parrotype.exe not found — build first")
        return 1

    temp = Path(tempfile.mkdtemp(prefix="parrotype_smoke_"))
    app_dir = temp / "app"
    data_dir = temp / "data"
    data_dir.mkdir()
    print(f"clean install dir: {app_dir}")
    shutil.copytree(DIST, app_dir)

    config = {
        "model_size": "tiny",
        "device": "cpu",
        "compute_type": "int8",
        "first_run_done": True,
        "sound_ticks": False,
    }
    (data_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")

    env = dict(os.environ)
    env["PARROTYPE_DATA_DIR"] = str(data_dir)
    proc = subprocess.Popen([str(app_dir / "Parrotype.exe")], env=env, cwd=str(app_dir))

    log_path = data_dir / "parrotype.log"
    deadline = time.monotonic() + WAIT_S
    model_ready = False
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            print(f"FAIL: process exited early (code {proc.returncode})")
            _dump_log(log_path)
            return 1
        if log_path.exists() and "Model ready" in log_path.read_text(encoding="utf-8", errors="replace"):
            model_ready = True
            break
        time.sleep(1)

    alive = proc.poll() is None
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    no_tracebacks = "Traceback" not in log_text

    print(f"{'PASS' if alive else 'FAIL'}: process alive after startup window")
    print(f"{'PASS' if model_ready else 'FAIL'}: model loaded (log 'Model ready')")
    print(f"{'PASS' if no_tracebacks else 'FAIL'}: no tracebacks in the log")

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(temp, ignore_errors=True)

    ok = alive and model_ready and no_tracebacks
    print("PASS: overall" if ok else "FAIL: overall")
    return 0 if ok else 1


def _dump_log(log_path: Path) -> None:
    if log_path.exists():
        print("--- log tail ---")
        print("\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]))


if __name__ == "__main__":
    sys.exit(main())
