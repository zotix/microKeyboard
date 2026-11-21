"""Standalone Hardware Flasher GUI for microKeyboard Layers 1..3 and persistent RGB LED."""

from __future__ import annotations

import json
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Optional

from . import __version__
from .gui import (
    _CLR_ACTIVE,
    _CLR_ACTIVE_HOVER,
    _CLR_CAPTURE,
    _CLR_CAPTURE_HOVER,
    _CLR_EXIT,
    _CLR_EXIT_HOVER,
    _CLR_REC_HOVER,
    _CLR_REC_IDLE,
    _CLR_RUNNING,
    _CLR_RUNNING_HOVER,
    APP_DIR,
    BUNDLE_DIR,
    SLOT_LABELS,
    RoundedButton,
    format_tk_keypress,
)
from .hid_transport import MicroKeyboardHID
from .protocol import (
    KEY_SLOTS,
    build_flash_key_packet,
    build_flash_led_packet,
    build_led_mode_packet,
    build_switch_layer_packet,
    combo_to_hid_packets,
)
from .tray_and_lock import SingleInstanceLock, focus_existing_window

FLASHER_TITLE = f"microKeyboard Hardware Flasher v{__version__}"
FLASHER_CONFIG_PATH = APP_DIR / "config" / "hardware_layers.json"
FLASHER_ICON_PATH = BUNDLE_DIR / "assets" / "microkeyboard_flasher.ico"

HARDWARE_PRESETS: list[str] = [
    "left",
    "right",
    "up",
    "down",
    "media_play_pause",
    "vol_up",
    "vol_down",
    "vol_mute",
    "media_next",
    "media_prev",
    "ctrl+c",
    "ctrl+v",
    "ctrl+z",
    "enter",
    "space",
]

DEFAULT_L1 = {
    "key1": "left",
    "key2": "media_play_pause",
    "key3": "right",
    "knob_ccw": "vol_down",
    "knob_cw": "vol_up",
    "knob_press": "vol_mute",
}

DEFAULT_L3 = {
    "key1": "ctrl+shift+alt+f1",
    "key2": "ctrl+shift+alt+f2",
    "key3": "ctrl+shift+alt+f3",
    "knob_ccw": "ctrl+shift+alt+f4",
    "knob_cw": "ctrl+shift+alt+f5",
    "knob_press": "ctrl+shift+alt+f6",
}


class FlasherApp:
    """Tkinter GUI for configuring and flashing hardware Layers 1..3 and LED mode."""

    def __init__(self, root: tk.Tk, config_path: Path = FLASHER_CONFIG_PATH) -> None:
        self.root = root
        self.config_path = config_path
        self.config: dict[str, Any] = self._load_config()
        self.current_layer: int = 1
        self._recording_slot: Optional[str] = None
        self._recording_btn: Optional[RoundedButton] = None

        self.root.title(FLASHER_TITLE)
        self.root.geometry("680x440")
        self.root.resizable(False, False)
        if FLASHER_ICON_PATH.exists():
            try:
                self.root.iconbitmap(default=str(FLASHER_ICON_PATH))
            except Exception:
                pass

        self._build_ui()
        self._load_layer_into_editor(1)

    def _load_config(self) -> dict[str, Any]:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        return {
            "led_mode": 1,
            "layers": {"1": dict(DEFAULT_L1), "2": dict(DEFAULT_L1), "3": dict(DEFAULT_L3)},
        }

    def _save_config_file(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self.config, indent=2) + "\n", encoding="utf-8")

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=14)
        main.pack(fill=tk.BOTH, expand=True)

        # Layer selector
        layer_frame = ttk.LabelFrame(main, text="Target Hardware Layer", padding=8)
        layer_frame.pack(fill=tk.X)
        self.var_layer = tk.IntVar(value=1)
        for layer_id, label in (
            (1, "Layer 1 (Standalone)"),
            (2, "Layer 2"),
            (3, "Layer 3 (Switcher)"),
        ):
            ttk.Radiobutton(
                layer_frame,
                text=label,
                value=layer_id,
                variable=self.var_layer,
                command=self._on_layer_change,
            ).pack(side=tk.LEFT, padx=(0, 18))

        # 6-Slot Hardware Keymap
        keys_frame = ttk.LabelFrame(main, text="Hardware Keymap (Single key/combo up to F12, or Media key)", padding=10)
        keys_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        keys_frame.columnconfigure(1, weight=1)

        self.slot_vars: dict[str, tk.StringVar] = {}
        self.rec_buttons: dict[str, RoundedButton] = {}
        for row_idx, (slot_key, label) in enumerate(SLOT_LABELS):
            ttk.Label(keys_frame, text=f"{label}:", width=11).grid(row=row_idx, column=0, sticky=tk.W, pady=4)
            var = tk.StringVar()
            self.slot_vars[slot_key] = var
            ttk.Entry(keys_frame, textvariable=var).grid(row=row_idx, column=1, sticky=tk.EW, padx=(4, 6), pady=4)

            rec_btn = RoundedButton(
                keys_frame,
                text="Rec",
                width=64,
                height=25,
                bg=_CLR_REC_IDLE,
                hover_bg=_CLR_REC_HOVER,
                command=lambda s=slot_key: self._start_record(s),
            )
            rec_btn.grid(row=row_idx, column=2, padx=(0, 4), pady=4)
            self.rec_buttons[slot_key] = rec_btn

            preset = ttk.Combobox(keys_frame, values=HARDWARE_PRESETS, state="readonly", width=17)
            preset.set("Preset...")
            preset.bind("<<ComboboxSelected>>", lambda _e, s=slot_key, cb=preset: self._apply_preset(s, cb))
            preset.grid(row=row_idx, column=3, pady=4)

        # Persistent RGB LED
        led_frame = ttk.LabelFrame(main, text="RGB LED (Commit to Flash)", padding=8)
        led_frame.pack(fill=tk.X, pady=(10, 0))
        self.var_led = tk.IntVar(value=int(self.config.get("led_mode", 1)))
        for val, lbl in ((0, "0: Off"), (1, "1: Key 1"), (2, "2: Cycle")):
            ttk.Radiobutton(led_frame, text=lbl, value=val, variable=self.var_led).pack(side=tk.LEFT, padx=(0, 14))
        RoundedButton(
            led_frame,
            text="Save LED",
            width=112,
            height=26,
            bg=_CLR_REC_IDLE,
            hover_bg=_CLR_REC_HOVER,
            command=self._flash_led_only,
        ).pack(side=tk.RIGHT)

        # Bottom Actions
        bottom = ttk.Frame(main)
        bottom.pack(fill=tk.X, pady=(12, 0))
        RoundedButton(
            bottom,
            text="Preset: L1 Default",
            width=136,
            height=28,
            bg=_CLR_REC_IDLE,
            hover_bg=_CLR_REC_HOVER,
            command=self._apply_l1_default,
        ).pack(side=tk.LEFT, padx=(0, 6))
        RoundedButton(
            bottom,
            text="Preset: L3 Switcher",
            width=136,
            height=28,
            bg=_CLR_CAPTURE,
            hover_bg=_CLR_CAPTURE_HOVER,
            command=self._apply_l3_default,
        ).pack(side=tk.LEFT)

        RoundedButton(
            bottom,
            text="Exit",
            width=96,
            height=28,
            bg=_CLR_EXIT,
            hover_bg=_CLR_EXIT_HOVER,
            command=self.root.destroy,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        RoundedButton(
            bottom,
            text="Flash Layer",
            width=124,
            height=28,
            bg=_CLR_RUNNING,
            hover_bg=_CLR_RUNNING_HOVER,
            command=self._flash_current_layer,
        ).pack(side=tk.RIGHT)

        self.var_status = tk.StringVar(value="Status: Ready (Saved local config)")
        ttk.Label(main, textvariable=self.var_status, font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(8, 0))

    def _load_layer_into_editor(self, layer_id: int) -> None:
        self.current_layer = layer_id
        layer_map = self.config.setdefault("layers", {}).get(str(layer_id), {})
        for slot_key, _ in SLOT_LABELS:
            self.slot_vars[slot_key].set(layer_map.get(slot_key, ""))

    def _collect_editor_to_layer(self, layer_id: int) -> Optional[dict[str, str]]:
        layer_map: dict[str, str] = {}
        for slot_key, label in SLOT_LABELS:
            val = self.slot_vars[slot_key].get().strip()
            if not val:
                messagebox.showerror("Missing Key", f"{label} cannot be empty.")
                return None
            try:
                combo_to_hid_packets(KEY_SLOTS[slot_key], val, layer=layer_id)
            except ValueError as exc:
                messagebox.showerror("Unsupported Hardware Key", f"{label}: {exc}")
                return None
            layer_map[slot_key] = val
        self.config.setdefault("layers", {})[str(layer_id)] = layer_map
        return layer_map

    def _on_layer_change(self) -> None:
        new_layer = int(self.var_layer.get())
        if new_layer == self.current_layer:
            return
        self.config.setdefault("layers", {})[str(self.current_layer)] = {
            s: self.slot_vars[s].get().strip() for s, _ in SLOT_LABELS
        }
        self._load_layer_into_editor(new_layer)
        self.var_status.set(f"Status: Editing Layer {new_layer}")

    def _cancel_record(self) -> None:
        if self._recording_btn is not None:
            self._recording_btn.configure(text="Rec", bg=_CLR_REC_IDLE, hover_bg=_CLR_REC_HOVER)
        self._recording_slot = None
        self._recording_btn = None
        self.root.unbind("<KeyPress>")

    def _start_record(self, slot_key: str) -> None:
        if self._recording_slot == slot_key:
            self._cancel_record()
            return
        self._cancel_record()
        self._recording_slot = slot_key
        btn = self.rec_buttons[slot_key]
        self._recording_btn = btn
        btn.configure(text="Press...", bg=_CLR_ACTIVE, hover_bg=_CLR_ACTIVE_HOVER)
        self.root.bind("<KeyPress>", self._on_record_keypress)

    def _on_record_keypress(self, event: tk.Event) -> str:
        combo = format_tk_keypress(event)
        if combo is None:
            return "break"
        if self._recording_slot:
            self.slot_vars[self._recording_slot].set(combo)
        self._cancel_record()
        return "break"

    def _apply_preset(self, slot_key: str, cb: ttk.Combobox) -> None:
        val = cb.get()
        if val and val != "Preset...":
            self.slot_vars[slot_key].set(val)
        cb.set("Preset...")

    def _apply_l1_default(self) -> None:
        for k, v in DEFAULT_L1.items():
            self.slot_vars[k].set(v)
        self.var_status.set("Status: Loaded Layer 1 Standalone defaults (click Flash Layer to write)")

    def _apply_l3_default(self) -> None:
        for k, v in DEFAULT_L3.items():
            self.slot_vars[k].set(v)
        self.var_status.set("Status: Loaded Layer 3 Switcher defaults (click Flash Layer to write)")

    def _flash_led_only(self) -> None:
        mode = int(self.var_led.get())
        try:
            with MicroKeyboardHID() as dev:
                dev.send(build_led_mode_packet(mode))
                time.sleep(0.05)
                dev.send(build_flash_led_packet())
            self.config["led_mode"] = mode
            self._save_config_file()
            self.var_status.set(f"Status: Committed LED Mode {mode} to Flash")
        except Exception as exc:
            messagebox.showerror("LED Flash Error", str(exc))

    def _flash_current_layer(self) -> None:
        layer_id = int(self.var_layer.get())
        layer_map = self._collect_editor_to_layer(layer_id)
        if layer_map is None:
            return
        try:
            with MicroKeyboardHID() as dev:
                dev.send(build_switch_layer_packet(layer_id))
                time.sleep(0.05)
                for slot_key, _ in SLOT_LABELS:
                    for pkt in combo_to_hid_packets(KEY_SLOTS[slot_key], layer_map[slot_key], layer=layer_id):
                        dev.send(pkt)
                        time.sleep(0.05)
                    dev.send(build_flash_key_packet())
                    time.sleep(0.05)
            self._save_config_file()
            self.var_status.set(f"Status: Flashed Layer {layer_id} & saved {self.config_path.name} (active on Layer {layer_id})")
        except Exception as exc:
            messagebox.showerror("Flash Error", str(exc))


def main() -> int:
    lock = SingleInstanceLock("Local\\MicroKeyboardFlasher_v1_1_0")
    if not lock.acquire():
        focus_existing_window(FLASHER_TITLE)
        return 0
    try:
        root = tk.Tk()
        FlasherApp(root)
        root.mainloop()
    finally:
        lock.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
