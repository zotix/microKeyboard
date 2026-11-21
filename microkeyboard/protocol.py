"""USB HID packet builders for the 3-key + 1-knob CH57x microKeyboard (VID 0x1189 / PID 0x8890).

Protocol constants and byte offsets are derived from the vendor's MINI KeyBoard.exe.
"""

from __future__ import annotations

REPORT_PAYLOAD_LEN = 64

# Key slot IDs (Data_Send_Buff[0])
KEY_SLOTS: dict[str, int] = {
    "key1": 1,
    "key2": 2,
    "key3": 3,
    "knob_ccw": 13,
    "knob_press": 14,
    "knob_cw": 15,
}

# USB HID Modifier bitmask
MOD_CTRL = 0x01
MOD_SHIFT = 0x02
MOD_ALT = 0x04
MOD_WIN = 0x08
MOD_CTRL_SHIFT_ALT = MOD_CTRL | MOD_SHIFT | MOD_ALT  # 0x07

MODIFIER_NAMES: dict[str, int] = {
    "ctrl": MOD_CTRL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT,
    "win": MOD_WIN,
}

# USB HID Keyboard Usage IDs (Page 0x07) supported by MINI KeyBoard.exe (up to F12 = 0x45)
HID_KEYCODES: dict[str, int] = {
    "enter": 0x28,
    "esc": 0x29,
    "backspace": 0x2A,
    "tab": 0x2B,
    "space": 0x2C,
    "-": 0x2D,
    "=": 0x2E,
    "[": 0x2F,
    "]": 0x30,
    "\\": 0x31,
    ";": 0x33,
    "'": 0x34,
    "`": 0x35,
    ",": 0x36,
    ".": 0x37,
    "/": 0x38,
    "f1": 0x3A,
    "f2": 0x3B,
    "f3": 0x3C,
    "f4": 0x3D,
    "f5": 0x3E,
    "f6": 0x3F,
    "f7": 0x40,
    "f8": 0x41,
    "f9": 0x42,
    "f10": 0x43,
    "f11": 0x44,
    "f12": 0x45,
    "delete": 0x4C,
    "home": 0x4A,
    "pgup": 0x4B,
    "end": 0x4D,
    "pgdn": 0x4E,
    "right": 0x4F,
    "left": 0x50,
    "down": 0x51,
    "up": 0x52,
}
for _idx, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
    HID_KEYCODES[_ch] = 0x04 + _idx
for _idx, _d in enumerate("123456789"):
    HID_KEYCODES[_d] = 0x1E + _idx
HID_KEYCODES["0"] = 0x27

# USB HID Consumer Control Usage IDs (ReportID=0x03, MULKey)
CONSUMER_CODES: dict[str, int] = {
    "play_pause": 0xCD,
    "media_play_pause": 0xCD,
    "mute": 0xE2,
    "vol_mute": 0xE2,
    "vol_up": 0xE9,
    "vol_down": 0xEA,
    "media_next": 0xB5,
    "media_prev": 0xB6,
}

# Note: This firmware only supports standard HID keycodes up to F12 (0x45), not F13..F18 (0x68..0x6D).
# Layer 3 is reserved for Switcher (Ctrl+Shift+Alt+F1..F6); Layer 1 is standalone hardware mode.
LAYER3_SWITCHER_MAPPING: list[tuple[str, int, int]] = [
    ("key1", MOD_CTRL_SHIFT_ALT, HID_KEYCODES["f1"]),
    ("key2", MOD_CTRL_SHIFT_ALT, HID_KEYCODES["f2"]),
    ("key3", MOD_CTRL_SHIFT_ALT, HID_KEYCODES["f3"]),
    ("knob_ccw", MOD_CTRL_SHIFT_ALT, HID_KEYCODES["f4"]),
    ("knob_cw", MOD_CTRL_SHIFT_ALT, HID_KEYCODES["f5"]),
    ("knob_press", MOD_CTRL_SHIFT_ALT, HID_KEYCODES["f6"]),
]
DEFAULT_BASE_MAPPING = LAYER3_SWITCHER_MAPPING

# Layer 1 standalone mapping: (slot_name, kind ["key"|"media"], val1 [mod|consumer], val2 [keycode|0])
LAYER1_STANDALONE_MAPPING: list[tuple[str, str, int, int]] = [
    ("key1", "key", 0x00, HID_KEYCODES["left"]),
    ("key2", "media", CONSUMER_CODES["play_pause"], 0x00),
    ("key3", "key", 0x00, HID_KEYCODES["right"]),
    ("knob_ccw", "media", CONSUMER_CODES["vol_down"], 0x00),
    ("knob_cw", "media", CONSUMER_CODES["vol_up"], 0x00),
    ("knob_press", "media", CONSUMER_CODES["mute"], 0x00),
]


def _make_payload(*head: int) -> bytes:
    """Create a 64-byte zero-padded HID payload starting with the given header bytes."""
    if len(head) > REPORT_PAYLOAD_LEN:
        raise ValueError(f"Payload exceeds {REPORT_PAYLOAD_LEN} bytes")
    buf = bytearray(REPORT_PAYLOAD_LEN)
    for idx, val in enumerate(head):
        buf[idx] = val & 0xFF
    return bytes(buf)


def build_probe_packet() -> bytes:
    """Build a 64-byte zero probe packet (mirrors KeyBoardVersion_Check)."""
    return _make_payload(0x00, 0x00)


def build_switch_layer_packet(layer: int) -> bytes:
    """Build a 64-byte command to switch the active hardware layer (1..3)."""
    if layer not in (1, 2, 3):
        raise ValueError("Layer must be 1, 2, or 3")
    return _make_payload(0xA1, layer)


def build_led_mode_packet(mode: int) -> bytes:
    """Build a 64-byte command to set the RGB LED mode (0, 1, or 2)."""
    if mode not in (0, 1, 2):
        raise ValueError("LED mode must be 0, 1, or 2")
    return _make_payload(0xB0, 0x08, mode)


def build_flash_led_packet() -> bytes:
    """Build a 64-byte command to commit LED settings to device flash."""
    return _make_payload(0xAA, 0xA1)


def build_key_packet(
    slot_id: int,
    modifier: int,
    keycode: int,
    layer: int = 1,
    group_len: int = 1,
    step_idx: int = 1,
) -> bytes:
    """Build a 64-byte key assignment packet for a specific step in a slot's sequence."""
    if slot_id not in KEY_SLOTS.values():
        raise ValueError(f"Unsupported key slot id: {slot_id}")
    if layer not in (1, 2, 3):
        raise ValueError("Layer must be 1, 2, or 3")
    key_type = ((layer & 0x0F) << 4) | 0x01 if layer > 1 else 0x01
    return _make_payload(slot_id, key_type, group_len, step_idx, modifier, keycode)


def build_single_key_packets(slot_id: int, modifier: int, keycode: int, layer: int = 1) -> list[bytes]:
    """Build the 2-step packet sequence (step 0: modifier, step 1: modifier+keycode) matching Download_Click."""
    return [
        build_key_packet(slot_id, modifier, 0x00, layer=layer, group_len=1, step_idx=0),
        build_key_packet(slot_id, modifier, keycode, layer=layer, group_len=1, step_idx=1),
    ]


def build_media_key_packet(slot_id: int, consumer_code: int, layer: int = 1) -> bytes:
    """Build a 64-byte command to assign a Consumer Control (multimedia) action to a slot."""
    if slot_id not in KEY_SLOTS.values():
        raise ValueError(f"Unsupported key slot id: {slot_id}")
    if layer not in (1, 2, 3):
        raise ValueError("Layer must be 1, 2, or 3")
    key_type = ((layer & 0x0F) << 4) | 0x02 if layer > 1 else 0x02
    return _make_payload(slot_id, key_type, consumer_code, 0x00)


def combo_to_hid_packets(slot_id: int, combo: str, layer: int = 1) -> list[bytes]:
    """Convert a human-readable key/media string (e.g. 'left', 'ctrl+c', 'vol_up') to HID packets."""
    tokens = [t.strip().lower() for t in combo.split("+") if t.strip()]
    if not tokens:
        raise ValueError("Empty key binding")
    if len(tokens) == 1 and tokens[0] in CONSUMER_CODES:
        return [build_media_key_packet(slot_id, CONSUMER_CODES[tokens[0]], layer=layer)]

    modifier = 0
    keycode: int | None = None
    for tok in tokens:
        if tok in MODIFIER_NAMES:
            modifier |= MODIFIER_NAMES[tok]
        elif tok in HID_KEYCODES:
            if keycode is not None:
                raise ValueError(f"Hardware slot supports 1 main key + modifiers, got: {combo!r}")
            keycode = HID_KEYCODES[tok]
        else:
            raise ValueError(f"Unsupported hardware key token: {tok!r}")
    if keycode is None:
        raise ValueError(f"Missing main key in: {combo!r}")
    return build_single_key_packets(slot_id, modifier, keycode, layer=layer)


def build_flash_key_packet() -> bytes:
    """Build a 64-byte command to commit keymap settings to device flash."""
    return _make_payload(0xAA, 0xAA)
