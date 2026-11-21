"""Single-instance Win32 mutex lock and System Tray icon (Shell_NotifyIconW)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import threading
from pathlib import Path
from typing import Callable, Optional

_ERROR_ALREADY_EXISTS = 183
_SW_RESTORE = 9
_WM_DESTROY = 0x0002
_WM_COMMAND = 0x0111
_WM_APP = 0x8000
_WM_TRAY = _WM_APP + 1
_WM_LBUTTONDBLCLK = 0x0203
_WM_LBUTTONUP = 0x0202
_WM_RBUTTONUP = 0x0205

_NIM_ADD = 0x00000000
_NIM_MODIFY = 0x00000001
_NIM_DELETE = 0x00000002
_NIF_MESSAGE = 0x00000001
_NIF_ICON = 0x00000002
_NIF_TIP = 0x00000004

_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010
_LR_DEFAULTSIZE = 0x0040
_IDI_APPLICATION = 32512

_MF_STRING = 0x0000
_MF_SEPARATOR = 0x0800
_TPM_RIGHTBUTTON = 0x0002

_CMD_OPEN = 1001
_CMD_TOGGLE = 1002
_CMD_EXIT = 1003

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)

_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.UINT),
        ("style", w.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", w.HINSTANCE),
        ("hIcon", w.HICON),
        ("hCursor", w.HANDLE),
        ("hbrBackground", w.HBRUSH),
        ("lpszMenuName", w.LPCWSTR),
        ("lpszClassName", w.LPCWSTR),
        ("hIconSm", w.HICON),
    ]


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("hWnd", w.HWND),
        ("uID", w.UINT),
        ("uFlags", w.UINT),
        ("uCallbackMessage", w.UINT),
        ("hIcon", w.HICON),
        ("szTip", w.WCHAR * 128),
        ("dwState", w.DWORD),
        ("dwStateMask", w.DWORD),
        ("szInfo", w.WCHAR * 256),
        ("uVersion", w.UINT),
        ("szInfoTitle", w.WCHAR * 64),
        ("dwInfoFlags", w.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", w.HICON),
    ]


_k32.CreateMutexW.restype = w.HANDLE
_k32.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
_k32.CloseHandle.argtypes = [w.HANDLE]
_k32.GetModuleHandleW.restype = w.HMODULE
_k32.GetModuleHandleW.argtypes = [w.LPCWSTR]

_user32.FindWindowW.restype = w.HWND
_user32.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
_user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
_user32.SetForegroundWindow.argtypes = [w.HWND]
_user32.RegisterClassExW.restype = w.ATOM
_user32.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSEXW)]
_user32.CreateWindowExW.restype = w.HWND
_user32.CreateWindowExW.argtypes = [
    w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    w.HWND, w.HMENU, w.HINSTANCE, ctypes.c_void_p,
]
_user32.DestroyWindow.argtypes = [w.HWND]
_user32.DefWindowProcW.restype = ctypes.c_ssize_t
_user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
_user32.LoadImageW.restype = w.HANDLE
_user32.LoadImageW.argtypes = [w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT]
_user32.LoadIconW.restype = w.HICON
_user32.LoadIconW.argtypes = [w.HINSTANCE, w.LPCWSTR]
_user32.CreatePopupMenu.restype = w.HMENU
_user32.AppendMenuW.argtypes = [w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR]
_user32.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, ctypes.c_void_p]
_user32.DestroyMenu.argtypes = [w.HMENU]
_user32.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
_user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
_user32.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
_user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
_user32.PostQuitMessage.argtypes = [ctypes.c_int]
_shell32.Shell_NotifyIconW.argtypes = [w.DWORD, ctypes.POINTER(_NOTIFYICONDATAW)]


class SingleInstanceLock:
    """Prevents multiple GUI instances using a named Win32 mutex."""

    def __init__(self, mutex_name: str = "Local\\MicroKeyboardGUI_v1_1_1") -> None:
        self.mutex_name = mutex_name
        self.handle: Optional[int] = None
        self.already_running = False

    def acquire(self) -> bool:
        handle = _k32.CreateMutexW(None, False, self.mutex_name)
        err = ctypes.get_last_error()
        self.handle = handle
        if err == _ERROR_ALREADY_EXISTS:
            self.already_running = True
            return False
        return bool(handle)

    def release(self) -> None:
        if self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None


def focus_existing_window(title: str) -> bool:
    """Try to restore and focus an existing window with the given title."""
    hwnd = _user32.FindWindowW(None, title)
    if hwnd:
        _user32.ShowWindow(hwnd, _SW_RESTORE)
        _user32.SetForegroundWindow(hwnd)
        return True
    return False


class Win32TrayIcon:
    """Background-thread Windows System Tray icon with context menu."""

    def __init__(
        self,
        tooltip: str,
        icon_path: Optional[Path],
        on_open: Callable[[], None],
        on_toggle_switcher: Callable[[], None],
        on_exit: Callable[[], None],
        is_switcher_running: Callable[[], bool],
    ) -> None:
        self.tooltip = tooltip[:127]
        self.icon_path = icon_path
        self.on_open = on_open
        self.on_toggle_switcher = on_toggle_switcher
        self.on_exit = on_exit
        self.is_switcher_running = is_switcher_running
        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def stop(self) -> None:
        if self._hwnd:
            _user32.PostMessageW(self._hwnd, _WM_DESTROY, 0, 0)

    def _load_hicon(self) -> int:
        if self.icon_path and self.icon_path.exists():
            hicon = _user32.LoadImageW(
                None, str(self.icon_path), _IMAGE_ICON, 16, 16, _LR_LOADFROMFILE | _LR_DEFAULTSIZE
            )
            if hicon:
                return hicon
        return _user32.LoadIconW(None, ctypes.cast(_IDI_APPLICATION, w.LPCWSTR))

    def _run_loop(self) -> None:
        hinst = _k32.GetModuleHandleW(None)
        cls_name = f"MicroKeyboardTrayWnd_{id(self)}"

        def _wnd_proc(hwnd: int, msg: int, wp: int, lp: int) -> int:
            if msg == _WM_TRAY:
                if lp in (_WM_LBUTTONDBLCLK, _WM_LBUTTONUP):
                    self.on_open()
                elif lp == _WM_RBUTTONUP:
                    self._show_menu(hwnd)
                return 0
            if msg == _WM_COMMAND:
                cmd = wp & 0xFFFF
                if cmd == _CMD_OPEN:
                    self.on_open()
                elif cmd == _CMD_TOGGLE:
                    self.on_toggle_switcher()
                elif cmd == _CMD_EXIT:
                    self.on_exit()
                return 0
            if msg == _WM_DESTROY:
                nid = _NOTIFYICONDATAW(cbSize=ctypes.sizeof(_NOTIFYICONDATAW), hWnd=hwnd, uID=1)
                _shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(nid))
                _user32.PostQuitMessage(0)
                return 0
            return _user32.DefWindowProcW(hwnd, msg, wp, lp)

        wndproc_ref = _WNDPROC(_wnd_proc)
        wc = _WNDCLASSEXW(
            cbSize=ctypes.sizeof(_WNDCLASSEXW),
            lpfnWndProc=wndproc_ref,
            hInstance=hinst,
            lpszClassName=cls_name,
        )
        _user32.RegisterClassExW(ctypes.byref(wc))
        hwnd = _user32.CreateWindowExW(0, cls_name, cls_name, 0, 0, 0, 0, 0, None, None, hinst, None)
        self._hwnd = hwnd

        hicon = self._load_hicon()
        nid = _NOTIFYICONDATAW(
            cbSize=ctypes.sizeof(_NOTIFYICONDATAW),
            hWnd=hwnd,
            uID=1,
            uFlags=_NIF_MESSAGE | _NIF_ICON | _NIF_TIP,
            uCallbackMessage=_WM_TRAY,
            hIcon=hicon,
            szTip=self.tooltip,
        )
        _shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(nid))
        self._ready.set()

        msg = w.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    def _show_menu(self, hwnd: int) -> None:
        menu = _user32.CreatePopupMenu()
        toggle_label = "Stop Switcher" if self.is_switcher_running() else "Start Switcher"
        _user32.AppendMenuW(menu, _MF_STRING, _CMD_OPEN, "Open microKeyboard GUI")
        _user32.AppendMenuW(menu, _MF_STRING, _CMD_TOGGLE, toggle_label)
        _user32.AppendMenuW(menu, _MF_SEPARATOR, 0, None)
        _user32.AppendMenuW(menu, _MF_STRING, _CMD_EXIT, "Exit")
        pt = w.POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        _user32.SetForegroundWindow(hwnd)
        _user32.TrackPopupMenu(menu, _TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, None)
        _user32.DestroyMenu(menu)
