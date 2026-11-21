"""Live key/knob tester using Win32 WH_KEYBOARD_LL to inspect incoming virtual key codes."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as w
import sys

_WH_KEYBOARD_LL = 13
_WM_KEYDOWN = 0x0100
_WM_SYSKEYDOWN = 0x0104
_WM_TIMER = 0x0113

_VK_NAMES: dict[int, str] = {
    0x7C: "F13",
    0x7D: "F14",
    0x7E: "F15",
    0x7F: "F16",
    0x80: "F17",
    0x81: "F18",
    0xAD: "VOLUME_MUTE",
    0xAE: "VOLUME_DOWN",
    0xAF: "VOLUME_UP",
    0xB0: "MEDIA_NEXT",
    0xB1: "MEDIA_PREV",
    0xB2: "MEDIA_STOP",
    0xB3: "MEDIA_PLAY_PAUSE",
}


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", w.DWORD),
        ("scanCode", w.DWORD),
        ("flags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, w.WPARAM, w.LPARAM)
_user32.SetWindowsHookExW.restype = w.HANDLE
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, w.HINSTANCE, w.DWORD]
_user32.CallNextHookEx.restype = ctypes.c_ssize_t
_user32.CallNextHookEx.argtypes = [w.HANDLE, ctypes.c_int, w.WPARAM, w.LPARAM]
_user32.UnhookWindowsHookEx.argtypes = [w.HANDLE]
_user32.SetTimer.argtypes = [w.HWND, ctypes.c_size_t, w.UINT, ctypes.c_void_p]
_user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
_user32.PostQuitMessage.argtypes = [ctypes.c_int]


def _vk_label(vk: int) -> str:
    if vk in _VK_NAMES:
        return _VK_NAMES[vk]
    if 0x30 <= vk <= 0x5A:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return f"0x{vk:02X}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor incoming keystrokes to verify microKeyboard output.")
    parser.add_argument("--seconds", type=int, default=0, help="Auto-exit after N seconds (0 = until Ctrl+C)")
    args = parser.parse_args()

    def _ll_proc(n_code: int, w_param: int, l_param: int) -> int:
        if n_code >= 0 and w_param in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            kb = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            injected = " [injected]" if (kb.flags & 0x10) else ""
            print(f"[Key] vk=0x{kb.vkCode:02X} ({_vk_label(kb.vkCode)}) scan=0x{kb.scanCode:02X}{injected}", flush=True)
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    cb = _HOOKPROC(_ll_proc)
    hook = _user32.SetWindowsHookExW(_WH_KEYBOARD_LL, cb, None, 0)
    if not hook:
        raise OSError(ctypes.get_last_error(), "SetWindowsHookExW failed")

    if args.seconds > 0:
        _user32.SetTimer(None, 1, args.seconds * 1000, None)
        print(f"Listening for key/knob presses for {args.seconds}s...", flush=True)
    else:
        print("Listening for key/knob presses (Ctrl+C to stop)...", flush=True)

    msg = w.MSG()
    try:
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == _WM_TIMER and args.seconds > 0:
                _user32.PostQuitMessage(0)
    except KeyboardInterrupt:
        pass
    finally:
        _user32.UnhookWindowsHookEx(hook)
    return 0


if __name__ == "__main__":
    sys.exit(main())
