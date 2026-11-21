"""Real-time per-app keymap & RGB LED switcher for microKeyboard (Pure Python Win32)."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as w
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .hid_transport import MicroKeyboardHID
from .protocol import build_led_mode_packet

_WH_KEYBOARD_LL = 13
_WM_KEYDOWN = 0x0100
_WM_KEYUP = 0x0101
_WM_SYSKEYDOWN = 0x0104
_WM_SYSKEYUP = 0x0105
_WM_QUIT = 0x0012
_WM_TIMER = 0x0113
_LLKHF_INJECTED = 0x10
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002

_TRIGGER_VKS: dict[int, str] = {
    0x70: "key1",        # Ctrl+Shift+Alt+F1
    0x71: "key2",        # Ctrl+Shift+Alt+F2
    0x72: "key3",        # Ctrl+Shift+Alt+F3
    0x73: "knob_ccw",    # Ctrl+Shift+Alt+F4
    0x74: "knob_cw",     # Ctrl+Shift+Alt+F5
    0x75: "knob_press",  # Ctrl+Shift+Alt+F6
}

VK_MAP: dict[str, int] = {
    "ctrl": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "win": 0x5B,
    "enter": 0x0D,
    "esc": 0x1B,
    "space": 0x20,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "pgup": 0x21,
    "pgdn": 0x22,
    "home": 0x24,
    "end": 0x23,
    "vol_mute": 0xAD,
    "vol_down": 0xAE,
    "vol_up": 0xAF,
    "media_next": 0xB0,
    "media_prev": 0xB1,
    "media_stop": 0xB2,
    "media_play_pause": 0xB3,
    "`": 0xC0,
    "/": 0xBF,
    "-": 0xBD,
    "=": 0xBB,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    ";": 0xBA,
    "'": 0xDE,
    ",": 0xBC,
    ".": 0xBE,
}
for _ch in "abcdefghijklmnopqrstuvwxyz":
    VK_MAP[_ch] = ord(_ch.upper())
for _d in "0123456789":
    VK_MAP[_d] = ord(_d)
for _n in range(1, 25):
    VK_MAP[f"f{_n}"] = 0x6F + _n


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", w.DWORD),
        ("scanCode", w.DWORD),
        ("flags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", w.WORD),
        ("wScan", w.WORD),
        ("dwFlags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("_pad", ctypes.c_byte * 28)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _INPUT_UNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, w.WPARAM, w.LPARAM)
_user32.SetWindowsHookExW.restype = w.HANDLE
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, w.HINSTANCE, w.DWORD]
_user32.CallNextHookEx.restype = ctypes.c_ssize_t
_user32.CallNextHookEx.argtypes = [w.HANDLE, ctypes.c_int, w.WPARAM, w.LPARAM]
_user32.UnhookWindowsHookEx.argtypes = [w.HANDLE]
_user32.SendInput.argtypes = [w.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
_user32.GetForegroundWindow.restype = w.HWND
_user32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
_user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
_user32.GetAsyncKeyState.restype = w.SHORT
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.SetTimer.argtypes = [w.HWND, ctypes.c_size_t, w.UINT, ctypes.c_void_p]
_user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
_user32.PostThreadMessageW.argtypes = [w.DWORD, w.UINT, w.WPARAM, w.LPARAM]
_k32.GetCurrentThreadId.restype = w.DWORD
_k32.OpenProcess.restype = w.HANDLE
_k32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
_k32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
_k32.CloseHandle.argtypes = [w.HANDLE]


def parse_combo(combo: str) -> list[int]:
    """Parse a shortcut string like 'ctrl+shift+t' into a list of Win32 VK codes."""
    tokens = [t.strip().lower() for t in combo.split("+") if t.strip()]
    vks = []
    for tok in tokens:
        if tok not in VK_MAP:
            raise ValueError(f"Unknown key token: {tok!r}")
        vks.append(VK_MAP[tok])
    return vks


def _all_trigger_mods_down() -> bool:
    """Return True when Ctrl, Shift, and Alt are all held (trigger signature)."""
    return all(_user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x11, 0x10, 0x12))


def send_combo(combo: str, release_trigger_mods: bool = False) -> None:
    """Send a key combination via Win32 SendInput."""
    vks = parse_combo(combo)
    if not vks:
        return
    events: list[tuple[int, int]] = []
    if release_trigger_mods:
        for mod_vk in (0x11, 0x10, 0x12):
            events.append((mod_vk, _KEYEVENTF_KEYUP))
    for vk in vks:
        events.append((vk, 0))
    for vk in reversed(vks):
        events.append((vk, _KEYEVENTF_KEYUP))
    inputs = (_INPUT * len(events))()
    for idx, (vk, flags) in enumerate(events):
        inputs[idx].type = _INPUT_KEYBOARD
        inputs[idx].u.ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    _user32.SendInput(len(inputs), inputs, ctypes.sizeof(_INPUT))


def get_foreground_info() -> tuple[str, str]:
    """Return (process_exe_name, window_title) for the current foreground window."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    title_buf = ctypes.create_unicode_buffer(512)
    _user32.GetWindowTextW(hwnd, title_buf, 512)
    pid = w.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    proc_name = ""
    if pid.value:
        hproc = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if hproc:
            try:
                path_buf = ctypes.create_unicode_buffer(1024)
                size = w.DWORD(1024)
                if _k32.QueryFullProcessImageNameW(hproc, 0, path_buf, ctypes.byref(size)):
                    proc_name = os.path.basename(path_buf.value)
            finally:
                _k32.CloseHandle(hproc)
    return proc_name, title_buf.value


def match_profile(process_name: str, window_title: str, config: dict[str, Any]) -> dict[str, Any]:
    """Select the best matching profile (title_regex > process > default)."""
    proc_lower = process_name.lower()
    profiles = config.get("profiles", [])

    # Pass 1: profiles with title_regex (most specific)
    for prof in profiles:
        regex = prof.get("title_regex")
        if not regex:
            continue
        req_proc = prof.get("process")
        if req_proc and req_proc.lower() != proc_lower:
            continue
        if re.search(regex, window_title, re.IGNORECASE):
            return prof

    # Pass 2: process-only profiles
    for prof in profiles:
        if prof.get("title_regex"):
            continue
        req_proc = prof.get("process")
        if req_proc and req_proc.lower() == proc_lower:
            return prof

    default = dict(config.get("default", {}))
    default.setdefault("name", "Default")
    return default


class ProfileSwitcher:
    """Manages active window tracking, LED updates, and Ctrl+Shift+Alt+F1..F6 key interception."""

    def __init__(
        self,
        config: dict[str, Any],
        use_led: bool = True,
        on_profile_change: Optional[Callable[[str, str, Optional[int]], None]] = None,
        on_key_event: Optional[Callable[[str, str, str], None]] = None,
    ) -> None:
        self.config = config
        self.use_led = use_led
        self.on_profile_change = on_profile_change
        self.on_key_event = on_key_event
        self.hid: Optional[MicroKeyboardHID] = None
        self.current_profile_name: Optional[str] = None
        self.current_led_mode: Optional[int] = None
        self.current_profile: dict[str, Any] = match_profile("", "", config)
        self._thread_id: Optional[int] = None

    def reload_config(self, new_config: dict[str, Any]) -> None:
        """Hot-reload profile config and force re-evaluation on next refresh."""
        self.config = new_config
        self.current_profile_name = None
        self.current_led_mode = None
        self.refresh_active_profile()

    def stop(self) -> None:
        """Signal the message loop on the running thread to exit cleanly."""
        if self._thread_id is not None:
            _user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)

    def connect_hid(self) -> None:
        if not self.use_led:
            return
        try:
            dev = MicroKeyboardHID()
            dev.open()
            self.hid = dev
            print(f"[HID] Connected MI_01 (ReportID=0x{dev.report_id:02X}) for per-app LED")
        except Exception as exc:
            print(f"[HID] Warning: LED sync disabled ({exc})")
            self.hid = None

    def close(self) -> None:
        if self.hid is not None:
            self.hid.close()
            self.hid = None

    def refresh_active_profile(self) -> None:
        proc, title = get_foreground_info()
        prof = match_profile(proc, title, self.config)
        self.current_profile = prof
        name = prof.get("name", "Default")
        if name != self.current_profile_name:
            self.current_profile_name = name
            print(f"[Profile] -> {name} (proc={proc or '-'})")
            led_mode = prof.get("led_mode")
            if self.hid is not None and led_mode is not None and led_mode != self.current_led_mode:
                try:
                    self.hid.send(build_led_mode_packet(int(led_mode)))
                    self.current_led_mode = int(led_mode)
                except Exception as exc:
                    print(f"[HID] LED update failed: {exc}")
            if self.on_profile_change is not None:
                self.on_profile_change(name, proc, int(led_mode) if led_mode is not None else None)

    def run(self) -> None:
        self._thread_id = _k32.GetCurrentThreadId()
        self.connect_hid()
        self.refresh_active_profile()

        def _ll_proc(n_code: int, w_param: int, l_param: int) -> int:
            if n_code >= 0:
                kb = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if kb.vkCode in _TRIGGER_VKS and not (kb.flags & _LLKHF_INJECTED) and _all_trigger_mods_down():
                    if w_param in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
                        self.refresh_active_profile()
                        trigger = _TRIGGER_VKS[kb.vkCode]
                        action = self.current_profile.get("keys", {}).get(trigger)
                        if action:
                            try:
                                send_combo(action, release_trigger_mods=True)
                                if self.on_key_event is not None:
                                    self.on_key_event(trigger, action, self.current_profile_name or "Default")
                            except Exception as exc:
                                print(f"[Send] Error for {trigger} -> {action}: {exc}")
                        return 1
                    if w_param in (_WM_KEYUP, _WM_SYSKEYUP):
                        return 1
            return _user32.CallNextHookEx(None, n_code, w_param, l_param)

        hook_cb = _HOOKPROC(_ll_proc)
        hook = _user32.SetWindowsHookExW(_WH_KEYBOARD_LL, hook_cb, None, 0)
        if not hook:
            raise OSError(ctypes.get_last_error(), "SetWindowsHookExW failed")

        _user32.SetTimer(None, 1, 250, None)
        msg = w.MSG()
        print("[Switcher] Running (Ctrl+C in terminal to stop)...")
        try:
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == _WM_TIMER:
                    self.refresh_active_profile()
        except KeyboardInterrupt:
            pass
        finally:
            _user32.UnhookWindowsHookEx(hook)
            self.close()
            self._thread_id = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Real-time per-app switcher for microKeyboard.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "config" / "profiles.json",
        help="Path to profiles.json",
    )
    parser.add_argument("--no-led", action="store_true", help="Disable per-app LED switching via MI_01")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    switcher = ProfileSwitcher(config, use_led=not args.no_led)
    switcher.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
