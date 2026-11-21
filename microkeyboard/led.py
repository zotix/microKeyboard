"""CLI to change RGB LED mode or active hardware layer on microKeyboard (MI_01)."""

from __future__ import annotations

import argparse
import sys

from .hid_transport import MicroKeyboardHID
from .protocol import (
    build_flash_led_packet,
    build_led_mode_packet,
    build_switch_layer_packet,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Control microKeyboard RGB LED mode and hardware layer.")
    parser.add_argument("--mode", type=int, choices=(0, 1, 2), help="RGB LED mode (0, 1, or 2)")
    parser.add_argument("--layer", type=int, choices=(1, 2, 3), help="Switch active hardware layer (1..3)")
    parser.add_argument("--no-flash", action="store_true", help="Send LED command without committing to flash")
    args = parser.parse_args()

    if args.mode is None and args.layer is None:
        parser.print_help()
        return 1

    with MicroKeyboardHID() as dev:
        print(f"Connected: {dev.path} (ReportID=0x{dev.report_id:02X})")
        if args.layer is not None:
            dev.send(build_switch_layer_packet(args.layer))
            print(f"Switched to layer {args.layer}")
        if args.mode is not None:
            dev.send(build_led_mode_packet(args.mode))
            if not args.no_flash:
                dev.send(build_flash_led_packet())
            print(f"Set LED mode {args.mode} (flash={'no' if args.no_flash else 'yes'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
