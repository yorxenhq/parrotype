"""PyInstaller entry point for the Parrotype tray application."""

import sys

from shells.tray.app import main

if __name__ == "__main__":
    sys.exit(main())
