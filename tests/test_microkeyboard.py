"""Unit tests for protocol packet builders, profile matching, and shortcut parsing."""

import json
import tkinter as tk
import unittest
from pathlib import Path

from microkeyboard import __version__, protocol, switcher
from microkeyboard.flash_gui import FlasherApp
from microkeyboard.gui import SwitcherApp
from microkeyboard.tray_and_lock import SingleInstanceLock
from microkeyboard.window_enum import RunningWindow, deduplicate_windows


class TestProtocol(unittest.TestCase):
    def test_packet_lengths(self) -> None:
        self.assertEqual(len(protocol.build_probe_packet()), 64)
        self.assertEqual(len(protocol.build_switch_layer_packet(1)), 64)
        self.assertEqual(len(protocol.build_led_mode_packet(2)), 64)
        self.assertEqual(len(protocol.build_flash_led_packet()), 64)
        self.assertEqual(len(protocol.build_key_packet(1, 0, 0x68)), 64)
        self.assertEqual(len(protocol.build_flash_key_packet()), 64)

    def test_led_and_flash_headers(self) -> None:
        led = protocol.build_led_mode_packet(2)
        self.assertEqual(led[:3], bytes([0xB0, 0x08, 0x02]))
        self.assertEqual(protocol.build_flash_led_packet()[:2], bytes([0xAA, 0xA1]))
        self.assertEqual(protocol.build_flash_key_packet()[:2], bytes([0xAA, 0xAA]))
        self.assertEqual(protocol.build_switch_layer_packet(3)[:3], bytes([0xA1, 0x03, 0x00]))

    def test_key_packet_layout(self) -> None:
        pkts = protocol.build_single_key_packets(
            protocol.KEY_SLOTS["knob_cw"],
            protocol.MOD_CTRL_SHIFT_ALT,
            protocol.HID_KEYCODES["f5"],
            layer=1,
        )
        self.assertEqual(len(pkts), 2)
        self.assertEqual(pkts[0][:6], bytes([15, 0x01, 0x01, 0x00, 0x07, 0x00]))
        self.assertEqual(pkts[1][:6], bytes([15, 0x01, 0x01, 0x01, 0x07, 0x3E]))

    def test_media_and_arrow_packets(self) -> None:
        play = protocol.build_media_key_packet(protocol.KEY_SLOTS["key2"], protocol.CONSUMER_CODES["play_pause"], layer=1)
        self.assertEqual(play[:4], bytes([2, 0x02, 0xCD, 0x00]))
        mute = protocol.build_media_key_packet(protocol.KEY_SLOTS["knob_press"], protocol.CONSUMER_CODES["mute"], layer=1)
        self.assertEqual(mute[:4], bytes([14, 0x02, 0xE2, 0x00]))
        left = protocol.build_single_key_packets(protocol.KEY_SLOTS["key1"], 0x00, protocol.HID_KEYCODES["left"], layer=1)
        self.assertEqual(left[1][:6], bytes([1, 0x01, 0x01, 0x01, 0x00, 0x50]))

    def test_default_profile_keys(self) -> None:
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "profiles.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(cfg["default"]["keys"]["key1"], "left")
        self.assertEqual(cfg["default"]["keys"]["key2"], "media_play_pause")
        self.assertEqual(cfg["default"]["keys"]["key3"], "right")

    def test_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            protocol.build_led_mode_packet(9)
        with self.assertRaises(ValueError):
            protocol.build_switch_layer_packet(0)
        with self.assertRaises(ValueError):
            protocol.build_key_packet(99, 0, 0x04)


class TestSwitcherLogic(unittest.TestCase):
    def setUp(self) -> None:
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "profiles.json"
        self.config = json.loads(cfg_path.read_text(encoding="utf-8"))

    def test_title_regex_priority(self) -> None:
        prof = switcher.match_profile("chrome.exe", "Funny Video - YouTube - Google Chrome", self.config)
        self.assertEqual(prof["name"], "Chrome - YouTube")

    def test_process_match(self) -> None:
        prof = switcher.match_profile("Code.exe", "switcher.py - microKeyboard", self.config)
        self.assertEqual(prof["name"], "VS Code")

    def test_default_fallback(self) -> None:
        prof = switcher.match_profile("unknown_app.exe", "Untitled", self.config)
        self.assertEqual(prof["name"], "Default")

    def test_parse_combo(self) -> None:
        self.assertEqual(switcher.parse_combo("ctrl+shift+t"), [0x11, 0x10, ord("T")])
        self.assertEqual(switcher.parse_combo("vol_up"), [0xAF])


class TestV110Features(unittest.TestCase):
    def test_version_is_1_1_1(self) -> None:
        self.assertEqual(__version__, "1.1.1")

    def test_window_dedup_and_sort(self) -> None:
        items = [
            RunningWindow("notepad.exe", "Untitled"),
            RunningWindow("Notepad.exe", "Untitled"),
            RunningWindow("Code.exe", "README.md"),
            RunningWindow("", "Hidden"),
            RunningWindow("chrome.exe", "   "),
        ]
        res = deduplicate_windows(items)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].process, "Code.exe")
        self.assertEqual(res[1].process.lower(), "notepad.exe")

    def test_single_instance_lock(self) -> None:
        name = "Local\\MicroKeyboardTestLock_Unit"
        lock1 = SingleInstanceLock(name)
        lock2 = SingleInstanceLock(name)
        self.assertTrue(lock1.acquire())
        self.assertFalse(lock2.acquire())
        self.assertTrue(lock2.already_running)
        lock2.release()
        lock1.release()

    def test_gui_headless_init(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = SwitcherApp(root, enable_tray=False)
            self.assertEqual(app.root.title(), "microKeyboard Switcher v1.1.1")
            self.assertFalse(app.is_switcher_running())
        finally:
            root.destroy()

    def test_combo_to_hid_packets_and_flasher_gui(self) -> None:
        pkts = protocol.combo_to_hid_packets(1, "ctrl+c", layer=1)
        self.assertEqual(len(pkts), 2)
        self.assertEqual(pkts[1][:6], bytes([1, 0x01, 0x01, 0x01, 0x01, 0x06]))

        media = protocol.combo_to_hid_packets(2, "media_play_pause", layer=1)
        self.assertEqual(len(media), 1)
        self.assertEqual(media[0][:4], bytes([2, 0x02, 0xCD, 0x00]))

        root = tk.Tk()
        root.withdraw()
        try:
            fapp = FlasherApp(root)
            self.assertEqual(fapp.root.title(), "microKeyboard Hardware Flasher v1.1.1")
            self.assertEqual(fapp.slot_vars["key1"].get(), "left")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
