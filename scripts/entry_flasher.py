"""PyInstaller entrypoint for microKeyboard Hardware Flasher GUI."""

import sys

from microkeyboard.flash_gui import main

if __name__ == "__main__":
    sys.exit(main())
