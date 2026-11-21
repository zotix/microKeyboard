"""Tkinter GUI v1.1.0 for editing Switcher profiles, picking real apps, testing LEDs, and tray control."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Optional

from . import __version__
from .hid_transport import MicroKeyboardHID
from .protocol import build_led_mode_packet
from .switcher import ProfileSwitcher, get_foreground_info, parse_combo
from .tray_and_lock import SingleInstanceLock, Win32TrayIcon, focus_existing_window
from .window_enum import RunningWindow, list_running_windows

APP_TITLE = f"microKeyboard Switcher v{__version__}"
ROOT_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT_DIR
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
DEFAULT_CONFIG_PATH = APP_DIR / "config" / "profiles.json"
ICON_PATH = BUNDLE_DIR / "assets" / "microkeyboard.ico"

SLOT_LABELS: list[tuple[str, str]] = [
    ("key1", "Key 1"),
    ("key2", "Key 2"),
    ("key3", "Key 3"),
    ("knob_ccw", "Knob CCW"),
    ("knob_cw", "Knob CW"),
    ("knob_press", "Knob Press"),
]

KEY_PRESETS: list[str] = [
    "ctrl+c",
    "ctrl+v",
    "ctrl+z",
    "ctrl+s",
    "ctrl+t",
    "ctrl+w",
    "ctrl+shift+t",
    "ctrl+shift+p",
    "alt+tab",
    "vol_up",
    "vol_down",
    "vol_mute",
    "media_play_pause",
    "media_next",
    "media_prev",
    "f5",
]

_TK_MOD_SYMS = {
    "Control_L",
    "Control_R",
    "Shift_L",
    "Shift_R",
    "Alt_L",
    "Alt_R",
    "Win_L",
    "Win_R",
    "Super_L",
    "Super_R",
}


def format_tk_keypress(event: tk.Event) -> Optional[str]:
    """Convert a Tkinter KeyPress event into a switcher combo string, or None for bare modifiers."""
    keysym = event.keysym
    if keysym in _TK_MOD_SYMS:
        return None
    parts: list[str] = []
    state = int(event.state)
    if state & 0x0004:
        parts.append("ctrl")
    if state & 0x0001:
        parts.append("shift")
    if state & 0x0008 or state & 0x20000:
        parts.append("alt")

    special = {
        "Return": "enter",
        "Escape": "esc",
        "BackSpace": "backspace",
        "Delete": "delete",
        "Prior": "pgup",
        "Next": "pgdn",
        "Up": "up",
        "Down": "down",
        "Left": "left",
        "Right": "right",
        "Home": "home",
        "End": "end",
        "Tab": "tab",
        "space": "space",
        "grave": "`",
        "slash": "/",
        "minus": "-",
        "equal": "=",
        "bracketleft": "[",
        "bracketright": "]",
        "backslash": "\\",
        "semicolon": ";",
        "apostrophe": "'",
        "comma": ",",
        "period": ".",
    }
    key_name = special.get(keysym, keysym.lower())
    parts.append(key_name)
    combo = "+".join(parts)
    parse_combo(combo)
    return combo


_CLR_IDLE = "#334155"
_CLR_IDLE_HOVER = "#475569"
_CLR_RUNNING = "#16A34A"
_CLR_RUNNING_HOVER = "#15803D"
_CLR_ACTIVE = "#D97706"
_CLR_ACTIVE_HOVER = "#B45309"
_CLR_CAPTURE = "#2563EB"
_CLR_CAPTURE_HOVER = "#1D4ED8"
_CLR_REC_IDLE = "#475569"
_CLR_REC_HOVER = "#64748B"
_CLR_EXIT = "#DC2626"
_CLR_EXIT_HOVER = "#B91C1C"
_CLR_DISABLED = "#94A3B8"


class RoundedButton(tk.Canvas):
    """Lightweight rounded-corner button widget for Tkinter with hover & state colors."""

    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: Any = None,
        bg: str = _CLR_IDLE,
        hover_bg: Optional[str] = None,
        fg: str = "white",
        width: int = 110,
        height: int = 28,
        radius: int = 8,
        font: tuple[str, int, str] = ("Segoe UI", 9, "bold"),
    ) -> None:
        try:
            parent_bg = parent.cget("background")
        except tk.TclError:
            parent_bg = ttk.Style().lookup("TFrame", "background") or "#F0F0F0"
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._text = text
        self._command = command
        self._bg = bg
        self._hover_bg = hover_bg or bg
        self._fg = fg
        self._btn_w = width
        self._btn_h = height
        self._r = radius
        self._font = font
        self._state = tk.NORMAL
        self._hovered = False

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_click)
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        fill = _CLR_DISABLED if self._state == tk.DISABLED else (self._hover_bg if self._hovered else self._bg)
        r = min(self._r, self._btn_w // 2, self._btn_h // 2)
        x1, y1, x2, y2 = 1, 1, self._btn_w - 1, self._btn_h - 1
        pts = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1, x2, y1 + r,
            x2, y2 - r,
            x2, y2, x2 - r, y2,
            x1 + r, y2,
            x1, y2, x1, y2 - r,
            x1, y1 + r,
            x1, y1, x1 + r, y1,
        ]
        self.create_polygon(pts, smooth=True, fill=fill, outline="")
        self.create_text(self._btn_w // 2, self._btn_h // 2, text=self._text, fill=self._fg, font=self._font)

    def _on_enter(self, _e: tk.Event) -> None:
        if self._state != tk.DISABLED:
            self._hovered = True
            self._redraw()

    def _on_leave(self, _e: tk.Event) -> None:
        self._hovered = False
        self._redraw()

    def _on_click(self, _e: tk.Event) -> None:
        if self._state != tk.DISABLED and self._command is not None:
            self._command()

    def configure(self, cnf: Any = None, **kw: Any) -> Any:  # type: ignore[override]
        if "text" in kw:
            self._text = kw.pop("text")
        if "bg" in kw:
            self._bg = kw.pop("bg")
        if "hover_bg" in kw:
            self._hover_bg = kw.pop("hover_bg")
        if "activebackground" in kw:
            self._hover_bg = kw.pop("activebackground")
        if "state" in kw:
            self._state = kw.pop("state")
            super().configure(cursor="" if self._state == tk.DISABLED else "hand2")
        if kw or cnf:
            super().configure(cnf, **kw)
        self._redraw()

    config = configure


class SwitcherApp:
    """Main Tkinter application window for microKeyboard Switcher."""

    def __init__(
        self,
        root: tk.Tk,
        config_path: Path = DEFAULT_CONFIG_PATH,
        enable_tray: bool = True,
        start_minimized: bool = False,
    ) -> None:
        self.root = root
        self.config_path = config_path
        self.enable_tray = enable_tray
        self.config: dict[str, Any] = self._load_config()
        self.selected_index: int = 0  # 0 = Default, 1..N = profiles[i-1]

        self.switcher: Optional[ProfileSwitcher] = None
        self.switcher_thread: Optional[threading.Thread] = None
        self._recording_slot: Optional[str] = None
        self._recording_btn: Optional[RoundedButton] = None
        self._capture_after_id: Optional[str] = None
        self._capture_popup: Optional[tk.Toplevel] = None
        self._tray: Optional[Win32TrayIcon] = None

        self.root.title(APP_TITLE)
        self.root.geometry("860x600")
        self.root.minsize(780, 540)
        if ICON_PATH.exists():
            try:
                self.root.iconbitmap(default=str(ICON_PATH))
            except Exception:
                pass

        self._build_ui()
        self._refresh_profile_list()
        self._load_selected_into_editor()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close_to_tray)
        self.root.bind("<Unmap>", self._on_unmap)

        if self.enable_tray:
            self._tray = Win32TrayIcon(
                tooltip=APP_TITLE,
                icon_path=ICON_PATH,
                on_open=lambda: self.root.after(0, self.restore_window),
                on_toggle_switcher=lambda: self.root.after(0, self.toggle_switcher),
                on_exit=lambda: self.root.after(0, self.exit_app),
                is_switcher_running=self.is_switcher_running,
            )
            self._tray.start()

        if start_minimized:
            self.toggle_switcher()
            self.hide_to_tray()

    def _load_config(self) -> dict[str, Any]:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        return {"default": {"led_mode": 1, "keys": {}}, "profiles": []}

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        top = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        top.pack(fill=tk.BOTH, expand=True)

        # Left Panel: Profiles
        left = ttk.LabelFrame(top, text="Profiles", padding=8)
        top.add(left, weight=1)

        self.profile_listbox = tk.Listbox(left, exportselection=False, width=24, font=("Segoe UI", 10))
        self.profile_listbox.pack(fill=tk.BOTH, expand=True)
        self.profile_listbox.bind("<<ListboxSelect>>", self._on_profile_select)

        btn_row = ttk.Frame(left)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_row, text="+ Add", width=7, command=self._add_profile).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_row, text="Dup", width=6, command=self._dup_profile).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_row, text="Del", width=6, command=self._del_profile).pack(side=tk.LEFT)

        ttk.Button(left, text="Save profiles.json", command=self._save_config).pack(fill=tk.X, pady=(8, 0))

        # Right Panel: Editor
        right = ttk.LabelFrame(top, text="Profile Editor", padding=10)
        top.add(right, weight=3)

        self.var_name = tk.StringVar()
        self.var_process = tk.StringVar()
        self.var_title = tk.StringVar()
        self.var_led = tk.IntVar(value=1)

        meta = ttk.Frame(right)
        meta.pack(fill=tk.X)
        meta.columnconfigure(1, weight=1)

        ttk.Label(meta, text="Name:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.entry_name = ttk.Entry(meta, textvariable=self.var_name)
        self.entry_name.grid(row=0, column=1, sticky=tk.EW, padx=6, pady=3)

        ttk.Label(meta, text="App (.exe):").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.entry_proc = ttk.Entry(meta, textvariable=self.var_process)
        self.entry_proc.grid(row=1, column=1, sticky=tk.EW, padx=6, pady=3)
        self.btn_pick_app = RoundedButton(
            meta, text="Pick App...", bg=_CLR_REC_IDLE, hover_bg=_CLR_REC_HOVER,
            width=112, height=26, command=self._open_app_picker,
        )
        self.btn_pick_app.grid(row=1, column=2, sticky=tk.E, padx=(2, 0), pady=3)

        ttk.Label(meta, text="Title Regex:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.entry_title = ttk.Entry(meta, textvariable=self.var_title)
        self.entry_title.grid(row=2, column=1, sticky=tk.EW, padx=6, pady=3)
        self.btn_capture = RoundedButton(
            meta, text="Capture 3s", bg=_CLR_CAPTURE, hover_bg=_CLR_CAPTURE_HOVER,
            width=112, height=26, command=self._start_capture_3s,
        )
        self.btn_capture.grid(row=2, column=2, sticky=tk.E, padx=(2, 0), pady=3)

        ttk.Label(meta, text="RGB LED:").grid(row=3, column=0, sticky=tk.W, pady=(8, 4))
        led_radios = ttk.Frame(meta)
        led_radios.grid(row=3, column=1, sticky=tk.W, padx=6, pady=(8, 4))
        for val, lbl in ((0, "0: Off"), (1, "1: Key 1"), (2, "2: Cycle")):
            ttk.Radiobutton(led_radios, text=lbl, value=val, variable=self.var_led).pack(side=tk.LEFT, padx=(0, 8))
        self.btn_test_led = RoundedButton(
            meta, text="Test LED", bg=_CLR_REC_IDLE, hover_bg=_CLR_REC_HOVER,
            width=112, height=26, command=self._test_led_now,
        )
        self.btn_test_led.grid(row=3, column=2, sticky=tk.E, padx=(2, 0), pady=(8, 4))

        keys_frame = ttk.LabelFrame(right, text="Keymap (6 Slots)", padding=8)
        keys_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        keys_frame.columnconfigure(1, weight=1)

        self.slot_vars: dict[str, tk.StringVar] = {}
        self.rec_buttons: dict[str, RoundedButton] = {}
        for row_idx, (slot_key, label) in enumerate(SLOT_LABELS):
            ttk.Label(keys_frame, text=f"{label}:", width=11).grid(row=row_idx, column=0, sticky=tk.W, pady=3)
            var = tk.StringVar()
            self.slot_vars[slot_key] = var
            ent = ttk.Entry(keys_frame, textvariable=var)
            ent.grid(row=row_idx, column=1, sticky=tk.EW, padx=(4, 6), pady=3)

            rec_btn = RoundedButton(
                keys_frame, text="Rec", width=64, height=25, bg=_CLR_REC_IDLE, hover_bg=_CLR_REC_HOVER,
                command=lambda s=slot_key: self._start_record(s),
            )
            rec_btn.grid(row=row_idx, column=2, padx=(0, 4), pady=3)
            self.rec_buttons[slot_key] = rec_btn

            preset = ttk.Combobox(keys_frame, values=KEY_PRESETS, state="readonly", width=15)
            preset.set("Preset...")
            preset.bind("<<ComboboxSelected>>", lambda _e, s=slot_key, cb=preset: self._apply_preset(s, cb))
            preset.grid(row=row_idx, column=3, pady=3)

        # Bottom Panel: Controls & Live Hardware Log
        bottom = ttk.Frame(main)
        bottom.pack(fill=tk.X, pady=(10, 0))

        ctrl = ttk.Frame(bottom)
        ctrl.pack(fill=tk.X)
        self.btn_toggle = RoundedButton(
            ctrl, text="Start Switcher", bg=_CLR_IDLE, hover_bg=_CLR_IDLE_HOVER,
            width=142, height=30, command=self.toggle_switcher,
        )
        self.btn_toggle.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(ctrl, text="Minimize to Tray", command=self.hide_to_tray).pack(side=tk.LEFT, padx=(0, 12))

        self.var_status = tk.StringVar(value="Status: Stopped | Active: -")
        ttk.Label(ctrl, textvariable=self.var_status, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.btn_exit = RoundedButton(
            ctrl, text="Exit", bg=_CLR_EXIT, hover_bg=_CLR_EXIT_HOVER,
            width=112, height=26, command=self.exit_app,
        )
        self.btn_exit.pack(side=tk.RIGHT)

        log_frame = ttk.LabelFrame(bottom, text="Live Hardware Log (press real keys/knob to verify)", padding=6)
        log_frame.pack(fill=tk.X, pady=(6, 0))
        self.log_box = scrolledtext.ScrolledText(log_frame, height=6, state=tk.DISABLED, font=("Consolas", 9))
        self.log_box.pack(fill=tk.X)

    def _append_log(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"{ts} {text}\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _refresh_profile_list(self) -> None:
        self.profile_listbox.delete(0, tk.END)
        self.profile_listbox.insert(tk.END, "* Default")
        for prof in self.config.get("profiles", []):
            self.profile_listbox.insert(tk.END, f"  {prof.get('name', 'Unnamed')}")
        self.profile_listbox.selection_clear(0, tk.END)
        self.profile_listbox.selection_set(self.selected_index)

    def _get_profile_obj(self, idx: int) -> dict[str, Any]:
        if idx == 0:
            return self.config.setdefault("default", {"led_mode": 1, "keys": {}})
        return self.config["profiles"][idx - 1]

    def _load_selected_into_editor(self) -> None:
        prof = self._get_profile_obj(self.selected_index)
        is_default = self.selected_index == 0
        self.var_name.set("Default" if is_default else prof.get("name", ""))
        self.var_process.set("" if is_default else prof.get("process", ""))
        self.var_title.set("" if is_default else prof.get("title_regex", ""))
        self.var_led.set(int(prof.get("led_mode", 1)))

        state = tk.DISABLED if is_default else tk.NORMAL
        self.entry_name.configure(state=state)
        self.entry_proc.configure(state=state)
        self.entry_title.configure(state=state)
        self.btn_pick_app.configure(state=state)
        self.btn_capture.configure(state=state)

        keys = prof.get("keys", {})
        for slot_key, _ in SLOT_LABELS:
            self.slot_vars[slot_key].set(keys.get(slot_key, ""))

    def _commit_editor_to_memory(self) -> bool:
        keys: dict[str, str] = {}
        for slot_key, label in SLOT_LABELS:
            val = self.slot_vars[slot_key].get().strip()
            if val:
                try:
                    parse_combo(val)
                except ValueError as exc:
                    messagebox.showerror("Invalid Key", f"{label}: {exc}")
                    return False
                keys[slot_key] = val

        prof = self._get_profile_obj(self.selected_index)
        prof["led_mode"] = int(self.var_led.get())
        prof["keys"] = keys
        if self.selected_index > 0:
            name = self.var_name.get().strip() or "Unnamed"
            prof["name"] = name
            proc = self.var_process.get().strip()
            if proc:
                prof["process"] = proc
            else:
                prof.pop("process", None)
            title = self.var_title.get().strip()
            if title:
                prof["title_regex"] = title
            else:
                prof.pop("title_regex", None)
        return True

    def _on_profile_select(self, _event: tk.Event) -> None:
        sel = self.profile_listbox.curselection()
        if not sel or sel[0] == self.selected_index:
            return
        if not self._commit_editor_to_memory():
            self.profile_listbox.selection_clear(0, tk.END)
            self.profile_listbox.selection_set(self.selected_index)
            return
        self.selected_index = sel[0]
        self._refresh_profile_list()
        self._load_selected_into_editor()

    def _add_profile(self) -> None:
        if not self._commit_editor_to_memory():
            return
        new_prof = {
            "name": "New App",
            "process": "",
            "led_mode": 1,
            "keys": copy.deepcopy(self.config.get("default", {}).get("keys", {})),
        }
        self.config.setdefault("profiles", []).append(new_prof)
        self.selected_index = len(self.config["profiles"])
        self._refresh_profile_list()
        self._load_selected_into_editor()

    def _dup_profile(self) -> None:
        if not self._commit_editor_to_memory():
            return
        src = copy.deepcopy(self._get_profile_obj(self.selected_index))
        src["name"] = f"{src.get('name', 'Profile')} Copy"
        self.config.setdefault("profiles", []).append(src)
        self.selected_index = len(self.config["profiles"])
        self._refresh_profile_list()
        self._load_selected_into_editor()

    def _del_profile(self) -> None:
        if self.selected_index == 0:
            messagebox.showinfo("Info", "Default profile cannot be deleted.")
            return
        self.config["profiles"].pop(self.selected_index - 1)
        self.selected_index = max(0, self.selected_index - 1)
        self._refresh_profile_list()
        self._load_selected_into_editor()

    def _save_config(self) -> None:
        if not self._commit_editor_to_memory():
            return
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self.config, indent=2) + "\n", encoding="utf-8")
        self._refresh_profile_list()
        self._append_log(f"[Config] Saved {self.config_path.name}")
        if self.switcher is not None and self.is_switcher_running():
            self.switcher.reload_config(copy.deepcopy(self.config))
            self._append_log("[Switcher] Hot-reloaded config")

    def _open_app_picker(self) -> None:
        windows = list_running_windows()
        dlg = tk.Toplevel(self.root)
        dlg.title("Pick Running Application")
        dlg.geometry("760x400")
        dlg.transient(self.root)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        xscroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL)
        yscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        lb = tk.Listbox(frame, font=("Consolas", 9), xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        xscroll.configure(command=lb.xview)
        yscroll.configure(command=lb.yview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        lb.pack(fill=tk.BOTH, expand=True)

        for item in windows:
            lb.insert(tk.END, f"{item.process:24s} | {item.title}")

        def _choose(_e: object = None) -> None:
            sel = lb.curselection()
            if not sel:
                return
            chosen: RunningWindow = windows[sel[0]]
            self.var_process.set(chosen.process)
            if self.var_name.get().strip() in ("", "New App"):
                self.var_name.set(chosen.process.removesuffix(".exe"))
            dlg.destroy()

        lb.bind("<Double-Button-1>", _choose)
        ttk.Button(dlg, text="Select", command=_choose).pack(pady=(0, 10))

    def _cancel_capture(self) -> None:
        if self._capture_after_id is not None:
            self.root.after_cancel(self._capture_after_id)
            self._capture_after_id = None
        if self._capture_popup is not None:
            try:
                self._capture_popup.destroy()
            except tk.TclError:
                pass
            self._capture_popup = None
        self.btn_capture.configure(text="Capture 3s", bg=_CLR_CAPTURE, hover_bg=_CLR_CAPTURE_HOVER)

    def _start_capture_3s(self) -> None:
        if self._capture_after_id is not None:
            self._cancel_capture()
            self._append_log("[Capture] Cancelled")
            return

        self.btn_capture.configure(text="Cancel (3s)", bg=_CLR_ACTIVE, hover_bg=_CLR_ACTIVE_HOVER)

        popup = tk.Toplevel(self.root)
        popup.title("Capture Active App")
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.geometry("300x105+40+40")
        popup.protocol("WM_DELETE_WINDOW", self._cancel_capture)
        self._capture_popup = popup

        lbl = ttk.Label(popup, text="Click target app window in 3s...", font=("Segoe UI", 10, "bold"))
        lbl.pack(pady=(14, 10))
        RoundedButton(
            popup, text="Cancel", bg=_CLR_EXIT, hover_bg=_CLR_EXIT_HOVER,
            width=96, height=26, command=self._cancel_capture,
        ).pack()

        def _tick(remaining: int) -> None:
            if self._capture_popup is None:
                return
            if remaining > 0:
                self.btn_capture.configure(text=f"Cancel ({remaining}s)", bg=_CLR_ACTIVE, hover_bg=_CLR_ACTIVE_HOVER)
                lbl.configure(text=f"Click target app window in {remaining}s...")
                self._capture_after_id = self.root.after(1000, _tick, remaining - 1)
                return

            self._cancel_capture()
            proc, title = get_foreground_info()
            if proc:
                self.var_process.set(proc)
                if self.var_name.get().strip() in ("", "New App"):
                    self.var_name.set(proc.removesuffix(".exe"))
            if title:
                self.var_title.set(title)
            self._append_log(f"[Capture] proc={proc} title={title}")

        _tick(3)

    def _test_led_now(self) -> None:
        mode = int(self.var_led.get())
        try:
            with MicroKeyboardHID() as dev:
                dev.send(build_led_mode_packet(mode))
            self._append_log(f"[LED] Previewed Mode {mode} (no-flash)")
        except Exception as exc:
            messagebox.showerror("LED Error", str(exc))

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

    def is_switcher_running(self) -> bool:
        return self.switcher_thread is not None and self.switcher_thread.is_alive()

    def toggle_switcher(self) -> None:
        if self.is_switcher_running():
            if self.switcher is not None:
                self.switcher.stop()
            self.btn_toggle.configure(text="Start Switcher", bg=_CLR_IDLE, hover_bg=_CLR_IDLE_HOVER)
            self.var_status.set("Status: Stopped | Active: -")
            self._append_log("[Switcher] Stopped")
            return

        if not self._commit_editor_to_memory():
            return
        cfg = copy.deepcopy(self.config)
        self.switcher = ProfileSwitcher(
            cfg,
            use_led=True,
            on_profile_change=lambda name, proc, led: self.root.after(
                0, self._on_sw_profile, name, proc, led
            ),
            on_key_event=lambda trig, act, pname: self.root.after(
                0, self._append_log, f"[Hardware] {trig} -> {act} ({pname})"
            ),
        )
        self.switcher_thread = threading.Thread(target=self.switcher.run, daemon=True)
        self.switcher_thread.start()
        self.btn_toggle.configure(text="Running (Stop)", bg=_CLR_RUNNING, hover_bg=_CLR_RUNNING_HOVER)
        self._append_log("[Switcher] Started")

    def _on_sw_profile(self, name: str, proc: str, led: Optional[int]) -> None:
        self.var_status.set(f"Status: Running | Active: {name}")
        led_txt = f" | LED Mode {led}" if led is not None else ""
        self._append_log(f"[Profile] -> {name} ({proc or '-'}){led_txt}")

    def hide_to_tray(self) -> None:
        if self.enable_tray:
            self.root.withdraw()
        else:
            self.root.iconify()

    def restore_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_unmap(self, event: tk.Event) -> None:
        if event.widget is self.root and self.root.state() == "iconic" and self.enable_tray:
            self.root.after(10, self.hide_to_tray)

    def _on_close_to_tray(self) -> None:
        if self.enable_tray:
            self.hide_to_tray()
        else:
            self.exit_app()

    def exit_app(self) -> None:
        if self.switcher is not None and self.is_switcher_running():
            self.switcher.stop()
        if self._tray is not None:
            self._tray.stop()
        self.root.quit()
        self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description="microKeyboard Switcher GUI")
    parser.add_argument("--minimized", action="store_true", help="Start minimized to System Tray with Switcher active")
    args = parser.parse_args()

    lock = SingleInstanceLock()
    if not lock.acquire():
        focus_existing_window(APP_TITLE)
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(APP_TITLE, "microKeyboard Switcher is already running (check System Tray).")
        root.destroy()
        return 0

    try:
        root = tk.Tk()
        SwitcherApp(root, start_minimized=args.minimized)
        root.mainloop()
    finally:
        lock.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
