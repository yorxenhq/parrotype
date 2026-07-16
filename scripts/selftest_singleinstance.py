"""Single-instance guard self-test (headless, no UI).

Process A holds the named mutex; process B runs the real app entry and
must exit with code 0 quickly, without creating a QApplication/tray
(PARROTYPE_SUPPRESS_SINGLETON_UI suppresses the MessageBox).

Run: python scripts/selftest_singleinstance.py -> PASS/FAIL, exit 0/1
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HOLDER = (
    "import sys, time; sys.path.insert(0, r'%s'); "
    "from shells.tray import singleinstance; "
    "assert singleinstance.acquire(); print('HELD', flush=True); time.sleep(30)"
) % ROOT


def main() -> int:
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER], stdout=subprocess.PIPE, text=True
    )
    line = holder.stdout.readline().strip()
    if line != "HELD":
        print("FAIL: holder process could not acquire the mutex")
        holder.kill()
        return 1
    print("PASS: first instance acquired the mutex")

    env = dict(os.environ)
    env["PARROTYPE_SUPPRESS_SINGLETON_UI"] = "1"
    env["PARROTYPE_DATA_DIR"] = str(
        Path(os.environ.get("TEMP", ".")) / "parrotype_singleton_test"
    )
    t0 = time.monotonic()
    second = subprocess.run(
        [sys.executable, "-m", "shells.tray"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=60,
    )
    elapsed = time.monotonic() - t0

    exited_zero = second.returncode == 0
    fast = elapsed < 30
    logged = "already running" in (second.stderr + second.stdout).lower()
    print(f"{'PASS' if exited_zero else 'FAIL'}: second instance exited with code {second.returncode}")
    print(f"{'PASS' if fast else 'FAIL'}: second instance exited quickly ({elapsed:.1f}s)")
    print(f"{'PASS' if logged else 'FAIL'}: second instance logged the reason")

    holder.kill()
    ok = exited_zero and fast and logged
    print("PASS: overall" if ok else "FAIL: overall")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
