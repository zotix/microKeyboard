"""Pure Python Win32 ctypes Raw HID transport for VID 0x1189 / PID 0x8890 (MI_01)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
from typing import Optional

from .protocol import REPORT_PAYLOAD_LEN, build_probe_packet

TARGET_VID_PID = "vid_1189&pid_8890"
TARGET_INTERFACE = "mi_01"
PROBE_REPORT_IDS = (0x00, 0x02, 0x03)

_DIGCF_PRESENT = 0x02
_DIGCF_DEVICEINTERFACE = 0x10
_GENERIC_READ_WRITE = 0xC0000000
_FILE_SHARE_RW = 0x03
_OPEN_EXISTING = 0x03
_INVALID_HANDLE = w.HANDLE(-1).value


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", w.DWORD),
        ("Data2", w.WORD),
        ("Data3", w.WORD),
        ("Data4", w.BYTE * 8),
    ]


class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("InterfaceClassGuid", _GUID),
        ("Flags", w.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]


_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
_hid = ctypes.WinDLL("hid", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(_GUID)]
_setupapi.SetupDiGetClassDevsW.restype = w.HANDLE
_setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(_GUID), w.LPCWSTR, w.HWND, w.DWORD]
_setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    w.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(_GUID),
    w.DWORD,
    ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
]
_setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    w.HANDLE,
    ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
    ctypes.c_void_p,
    w.DWORD,
    ctypes.POINTER(w.DWORD),
    ctypes.c_void_p,
]
_setupapi.SetupDiDestroyDeviceInfoList.argtypes = [w.HANDLE]

_k32.CreateFileW.restype = w.HANDLE
_k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
_k32.WriteFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
_k32.CloseHandle.argtypes = [w.HANDLE]


def find_mi01_path() -> Optional[str]:
    """Return the Windows HID device path for VID_1189&PID_8890&MI_01, or None."""
    guid = _GUID()
    _hid.HidD_GetHidGuid(ctypes.byref(guid))
    hdev = _setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, _DIGCF_PRESENT | _DIGCF_DEVICEINTERFACE
    )
    if hdev == _INVALID_HANDLE:
        return None
    try:
        did = _SP_DEVICE_INTERFACE_DATA(cbSize=ctypes.sizeof(_SP_DEVICE_INTERFACE_DATA))
        idx = 0
        while _setupapi.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(guid), idx, ctypes.byref(did)):
            idx += 1
            req = w.DWORD(0)
            _setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), None, 0, ctypes.byref(req), None)
            buf = ctypes.create_string_buffer(req.value)
            ctypes.cast(buf, ctypes.POINTER(w.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if _setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), buf, req.value, None, None):
                path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                lower = path.lower()
                if TARGET_VID_PID in lower and TARGET_INTERFACE in lower:
                    return path
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return None


class MicroKeyboardHID:
    """Context-managed Raw HID connection to microKeyboard MI_01."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or find_mi01_path()
        self.handle: Optional[int] = None
        self.report_id: Optional[int] = None

    def open(self) -> None:
        if not self.path:
            raise FileNotFoundError("microKeyboard MI_01 (VID 0x1189 / PID 0x8890) not found")
        handle = _k32.CreateFileW(
            self.path, _GENERIC_READ_WRITE, _FILE_SHARE_RW, None, _OPEN_EXISTING, 0, None
        )
        if handle == _INVALID_HANDLE:
            err = ctypes.get_last_error()
            raise OSError(err, f"Failed to open {self.path} (win32 err={err})")
        self.handle = handle
        self.report_id = self._probe_report_id()

    def close(self) -> None:
        if self.handle is not None:
            _k32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "MicroKeyboardHID":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _probe_report_id(self) -> int:
        probe = build_probe_packet()
        for rid in PROBE_REPORT_IDS:
            if self._write_raw(rid, probe):
                return rid
        raise OSError("Device did not accept any probed ReportID (0x00, 0x02, 0x03)")

    def _write_raw(self, report_id: int, payload: bytes) -> bool:
        if self.handle is None:
            raise RuntimeError("Device is not open")
        if len(payload) != REPORT_PAYLOAD_LEN:
            raise ValueError(f"Expected {REPORT_PAYLOAD_LEN}-byte payload, got {len(payload)}")
        frame = bytes([report_id & 0xFF]) + payload
        written = w.DWORD(0)
        ok = _k32.WriteFile(self.handle, frame, len(frame), ctypes.byref(written), None)
        return bool(ok) and written.value == len(frame)

    def send(self, payload: bytes) -> None:
        if self.report_id is None:
            raise RuntimeError("Device ReportID not initialized")
        if not self._write_raw(self.report_id, payload):
            err = ctypes.get_last_error()
            raise OSError(err, f"WriteFile failed (win32 err={err})")
