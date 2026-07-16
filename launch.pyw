"""Windowless launcher for autostart (referenced by the HKCU Run key)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shells.tray.app import main  # noqa: E402

sys.exit(main())
