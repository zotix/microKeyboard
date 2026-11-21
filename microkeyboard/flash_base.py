"""Flash programmer for Dual-Layer setup: Layer 1 (Standalone) and Layer 3 (Switcher)."""

from __future__ import annotations

import argparse
import sys
import time

from .hid_transport import MicroKeyboardHID
from .protocol import (
    KEY_SLOTS,
    LAYER1_STANDALONE_MAPPING,
    LAYER3_SWITCHER_MAPPING,
    build_flash_key_packet,
    build_media_key_packet,
    build_single_key_packets,
    build_switch_layer_packet,
)


def build_layer1_packets() -> list[tuple[str, bytes]]:
    """Build packets for Layer 1 standalone mode (Left, Play/Pause, Right, Vol-, Vol+, Mute)."""
    pkts: list[tuple[str, bytes]] = [("switch_layer(1)", build_switch_layer_packet(1))]
    for name, kind, val1, val2 in LAYER1_STANDALONE_MAPPING:
        slot_id = KEY_SLOTS[name]
        if kind == "key":
            for idx, pkt in enumerate(build_single_key_packets(slot_id, val1, val2, layer=1)):
                pkts.append((f"L1:{name}[{idx}] -> key=0x{val2:02X}", pkt))
        else:
            pkts.append((f"L1:{name} -> media=0x{val1:02X}", build_media_key_packet(slot_id, val1, layer=1)))
        pkts.append((f"commit_flash(L1:{name})", build_flash_key_packet()))
    return pkts


def build_layer_switcher_packets(layer: int = 3) -> list[tuple[str, bytes]]:
    """Build packets for Switcher mode (Ctrl+Shift+Alt+F1..F6) on the target layer."""
    pkts: list[tuple[str, bytes]] = [(f"switch_layer({layer})", build_switch_layer_packet(layer))]
    for name, mod, keycode in LAYER3_SWITCHER_MAPPING:
        slot_id = KEY_SLOTS[name]
        for idx, pkt in enumerate(build_single_key_packets(slot_id, mod, keycode, layer=layer)):
            pkts.append((f"L{layer}:{name}[{idx}] -> mod=0x{mod:02X} key=0x{keycode:02X}", pkt))
        pkts.append((f"commit_flash(L{layer}:{name})", build_flash_key_packet()))
    return pkts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Program microKeyboard Layer 1 (Standalone) and Layer 3 (Switcher)."
    )
    parser.add_argument(
        "--preset",
        choices=("switcher-l1", "standalone-l1", "dual"),
        default="switcher-l1",
        help="Preset to flash (default: switcher-l1 -> Ctrl+Shift+Alt+F1..F6 on Layer 1)",
    )
    parser.add_argument("--layer", type=int, choices=(1, 2, 3), help="Override target layer for Switcher mapping")
    parser.add_argument("--dry-run", action="store_true", help="Print packets without writing to the device")
    args = parser.parse_args()

    packets: list[tuple[str, bytes]] = []
    if args.layer is not None:
        packets.extend(build_layer_switcher_packets(args.layer))
    elif args.preset == "standalone-l1":
        packets.extend(build_layer1_packets())
    elif args.preset == "dual":
        packets.extend(build_layer_switcher_packets(3))
        packets.extend(build_layer1_packets())
    else:
        packets.extend(build_layer_switcher_packets(1))

    if args.dry_run:
        print(f"[DRY-RUN] Preset={args.preset} ({len(packets)} packets):")
        for label, pkt in packets:
            print(f"  {label:38s}: {pkt[:8].hex(' ')} ...")
        return 0

    with MicroKeyboardHID() as dev:
        print(f"Connected: {dev.path} (ReportID=0x{dev.report_id:02X})")
        for label, pkt in packets:
            dev.send(pkt)
            time.sleep(0.05)
            print(f"  Sent {label}")
    print("Done! Flashed successfully (currently active on Layer 1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
