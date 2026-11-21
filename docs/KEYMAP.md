# microKeyboard Keymap Reference (`v1.1.1`)

> **Hardware / Firmware Note:** Testing on real hardware confirmed that `0xA1 <layer> 0x00` only selects the target layer during flash programming — the stock firmware **does not support switching the active runtime layer over USB HID**. Therefore, **Layer 1** is programmed with `Ctrl+Shift+Alt+F1..F6` by default (`--preset switcher-l1`) so `switcher.py` / `gui.py` work immediately, while the `Default` profile in `config/profiles.json` provides `Left / Play-Pause / Right / Vol- / Vol+ / Mute`.

---

## 1. Standalone Hardware Preset (`--preset standalone-l1` / `config/hardware_layers.json` Layer 1)

| Physical Control | Slot Name | Slot ID | Action | Protocol Type / Code |
|---|---|---|---|---|
| **Key 1** | `key1` | `1` (`0x01`) | **Arrow Left** | Keyboard (`0x01`) / `0x50` |
| **Key 2** | `key2` | `2` (`0x02`) | **Media Play / Pause** | Consumer (`0x02`) / `0xCD` |
| **Key 3** | `key3` | `3` (`0x03`) | **Arrow Right** | Keyboard (`0x01`) / `0x4F` |
| **Knob Turn Left (CCW)** | `knob_ccw` | `13` (`0x0D`) | **Volume Down** | Consumer (`0x02`) / `0xEA` |
| **Knob Turn Right (CW)** | `knob_cw` | `15` (`0x0F`) | **Volume Up** | Consumer (`0x02`) / `0xE9` |
| **Knob Press** | `knob_press` | `14` (`0x0E`) | **Mute** | Consumer (`0x02`) / `0xE2` |

---

## 2. Switcher Base Signals (Default Layer 1 via `python -m microkeyboard.flash_base`)

All 3 mechanical keys and 3 rotary knob actions emit a unique `Ctrl+Shift+Alt+F1..F6` signature on **Layer 3** so they never conflict with normal applications and stay within the firmware's `F1..F12` (`0x3A..0x45`) keycode limit.

| Physical Control | Slot Name | Protocol Slot ID | Flashed Signal | HID Mod / Usage ID | Win32 VK Code |
|---|---|---|---|---|---|
| **Key 1** | `key1` | `1` (`0x01`) | `Ctrl+Shift+Alt+F1` | `0x07` / `0x3A` | `0xA2+0xA0+0xA4+0x70` |
| **Key 2** | `key2` | `2` (`0x02`) | `Ctrl+Shift+Alt+F2` | `0x07` / `0x3B` | `0xA2+0xA0+0xA4+0x71` |
| **Key 3** | `key3` | `3` (`0x03`) | `Ctrl+Shift+Alt+F3` | `0x07` / `0x3C` | `0xA2+0xA0+0xA4+0x72` |
| **Knob Turn Left (CCW)** | `knob_ccw` | `13` (`0x0D`) | `Ctrl+Shift+Alt+F4` | `0x07` / `0x3D` | `0xA2+0xA0+0xA4+0x73` |
| **Knob Turn Right (CW)** | `knob_cw` | `15` (`0x0F`) | `Ctrl+Shift+Alt+F5` | `0x07` / `0x3E` | `0xA2+0xA0+0xA4+0x74` |
| **Knob Press** | `knob_press` | `14` (`0x0E`) | `Ctrl+Shift+Alt+F6` | `0x07` / `0x3F` | `0xA2+0xA0+0xA4+0x75` |

---

## 2. Per-App Keymap & RGB LED Table (`config/profiles.json`)

When `python -m microkeyboard.switcher` is running, incoming `key1..knob_press` signals are translated in real time (`0 ms`) based on the active window's **Process** and **Title Regex** (priority: `title_regex` > `process` > `Default`).

| Control | Default (`led: 0`) | VS Code (`Code.exe`, `led: 0`) | Chrome - YouTube (`chrome.exe` + `YouTube`, `led: 0`) | Chrome (`chrome.exe`, `led: 0`) | Notepad (`notepad.exe`, `led: 0`) |
|---|---|---|---|---|---|
| **Key 1** (`key1`) | `left` | `ctrl+shift+p` (Command Palette) | `j` (Rewind 10s) | `ctrl+t` (New Tab) | `ctrl+s` (Save) |
| **Key 2** (`key2`) | `media_play_pause` | `ctrl+/` (Toggle Comment) | `media_play_pause` | `ctrl+w` (Close Tab) | `ctrl+f` (Find) |
| **Key 3** (`key3`) | `right` | `f5` (Start Debugging) | `l` (Forward 10s) | `ctrl+shift+t` (Reopen Tab) | `ctrl+a` (Select All) |
| **Knob CCW** (`knob_ccw`) | `vol_down` | `ctrl+-` (Zoom Out) | `ctrl+pgup` (Prev Tab) | `ctrl+pgup` (Prev Tab) | `ctrl+-` (Zoom Out) |
| **Knob CW** (`knob_cw`) | `vol_up` | `ctrl+=` (Zoom In) | `ctrl+pgdn` (Next Tab) | `ctrl+pgdn` (Next Tab) | `ctrl+=` (Zoom In) |
| **Knob Press** (`knob_press`) | `vol_mute` | ``ctrl+` `` (Toggle Terminal) | `ctrl+r` (Reload) | `ctrl+r` (Reload) | `ctrl+n` (New Window) |

---

## 3. RGB LED Modes (Firmware Hardware Limits)

| `led_mode` | Behavior Observed on Hardware |
|---|---|
| `0` | Off (no light) |
| `1` | Solid light on first key |
| `2` | Running color cycle |
