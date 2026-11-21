"""Win32 visible window & running process enumerator for the GUI app picker."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import os
from dataclasses import dataclass

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_WNDENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
_user32.EnumWindows.argtypes = [_WNDENUMPROC, w.LPARAM]
_user32.IsWindowVisible.argtypes = [w.HWND]
_user32.GetWindowTextLengthW.argtypes = [w.HWND]
_user32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
_user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
_k32.OpenProcess.restype = w.HANDLE
_k32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
_k32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
_k32.CloseHandle.argtypes = [w.HANDLE]


@dataclass(frozen=True)
class RunningWindow:
    """Represents a visible top-level application window."""

    process: str
    title: str


def deduplicate_windows(items: list[RunningWindow]) -> list[RunningWindow]:
    """Deduplicate by (lowercase process, title) and sort by process then title."""
    seen: set[tuple[str, str]] = set()
    result: list[RunningWindow] = []
    for item in items:
        if not item.process or not item.title.strip():
            continue
        key = (item.process.lower(), item.title.strip())
        if key in seen:
            continue
        seen.add(key)
        result.append(RunningWindow(process=item.process, title=item.title.strip()))
    result.sort(key=lambda w_item: (w_item.process.lower(), w_item.title.lower()))
    return result


def list_running_windows() -> list[RunningWindow]:
    """Enumerate all visible top-level windows with a non-empty title and process name."""
    collected: list[RunningWindow] = []

    def _cb(hwnd: int, _lparam: int) -> bool:
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        pid = w.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc_name = ""
        if pid.value:
            hproc = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if hproc:
                try:
                    pbuf = ctypes.create_unicode_buffer(1024)
                    size = w.DWORD(1024)
                    if _k32.QueryFullProcessImageNameW(hproc, 0, pbuf, ctypes.byref(size)):
                        proc_name = os.path.basename(pbuf.value)
                finally:
                    _k32.CloseHandle(hproc)
        if proc_name:
            collected.append(RunningWindow(process=proc_name, title=title))
        return True

    cb = _WNDENUMPROC(_cb)
    _user32.EnumWindows(cb, 0)
    return deduplicate_windows(collected)
