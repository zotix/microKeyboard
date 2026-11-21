# microKeyboard (3-Key + 1-Knob RGB Macro Pad)

Pure Python (`ctypes` + Win32 API, zero third-party dependencies) toolkit to configure and automate a **CH57x-based 3-key + 1-knob RGB macro pad** (`VID 0x1189 / PID 0x8890`).

---

## 1. Project Status

- **Hardware Detection & `MI_01` Access (Verified)**: Device is connected (`Status: OK`). Auto-probe resolves `ReportID = 0x03`, and `MI_01` (`UsagePage 0xFF00`) opens for Read/Write via Win32 `CreateFileW` (`err: 0`) without extra drivers (no Zadig) or Administrator privileges.
- **Software & Tests (Verified)**:
  - Unit tests (`test_microkeyboard.py`): **8/8 passed**
  - Dry-run keymap flasher (`flash_base.py --dry-run`): **passed**
  - Live `MI_01` LED command (`led.py --mode 0|1|2 --no-flash`): **passed** (`ReportID=0x03`)

---

## 2. Measured Hardware & USB / HID Descriptors

- **Device Instance ID**: `USB\VID_1189&PID_8890\5&129774C1&0&8`
- **Vendor ID / Product ID**: `0x1189` / `0x8890` (WCH CH57x family)
- **Version**: `0x0000`
- **USB String Descriptors**: `Manufacturer = ''`, `Product = ''`, `Serial = ''` *(not populated by stock firmware)*
- **Physical Layout** *(user-confirmed)*: 3 mechanical keys + 1 rotary encoder knob + RGB LEDs

### USB Interfaces (4 Interfaces / 5 HID Collections)

| Interface | Windows Device Type | UsagePage | Usage | Report Length (In / Out / Feat) | Purpose |
|---|---|---|---|---|---|
| `MI_00` | HID Keyboard Device | `0x0001` (Generic Desktop) | `0x0006` (Keyboard) | `9 / 2 / 0` bytes | Standard 6KRO keyboard + LED output |
| `MI_01` | HID-compliant vendor-defined device | `0xFF00` (Vendor-Defined) | `0x0001` | `65 / 65 / 0` bytes | **Raw HID config channel** (1-byte Report ID + 64-byte payload) for Keymap / Macro / Layer / RGB |
| `MI_02&COL01` | HID Keyboard Device | `0x0001` (Generic Desktop) | `0x0006` (Keyboard) | `12 / 2 / 0` bytes | Extended keyboard report |
| `MI_02&COL02` | HID-compliant consumer control device | `0x000C` (Consumer) | `0x0001` (Consumer Control) | `3 / 0 / 0` bytes | Media / Volume keys (Play, Pause, Vol+, Vol-, Mute) |
| `MI_03` | HID-compliant mouse | `0x0001` (Generic Desktop) | `0x0002` (Mouse) | `5 / 0 / 0` bytes | Mouse emulation (clicks / scroll) |

---

## 3. Extracted Raw HID Protocol (`MINI KeyBoard.exe`)

Derived by inspecting `HIDTester.FormMain`, `HIDTester.LEDkey`, `HIDTester.HidLib`, and `HIDTester.FormMain+KeyParam` in the vendor binary (`MINI KeyBoard.exe`, uses `HidLibrary.dll`).

- **Report ID Probe Order**: `0x00`, `0x02`, `0x03` (this device accepts **`0x03`**)
- **Frame Size**: `65 bytes` (`[ReportID]` + `64-byte zero-padded payload`)
- **Key Slot IDs (`payload[0]`)**:
  - `KEY1` = `1`, `KEY2` = `2`, `KEY3` = `3`
  - `Knob CCW` = `13` (`0x0D`), `Knob Press` = `14` (`0x0E`), `Knob CW` = `15` (`0x0F`)
- **Commands**:
  - **Switch Layer (`1..3`)**: `A1 <layer> 01 ...`
  - **Assign Single Keyboard Key**: sends 2 packets (`step=0` with `<modifier>, 0x00` then `step=1` with `<modifier>, <hid_keycode>`) as `<slot> <key_type> 01 <step> <modifier> <hid_keycode> ...` *(commit to flash with `AA AA ...`)*
  - **Set RGB LED Mode (`0|1|2`)**: `B0 08 <mode> ...` *(commit to flash with `AA A1 ...`)*

### Community Open-Source References (`0x1189:0x8890`)
- **Rust CLI**: [kriomant/ch57x-keyboard-tool](https://github.com/kriomant/ch57x-keyboard-tool)
- **WebHID**: [pollrobots/ch57x-programmer](https://github.com/pollrobots/ch57x-programmer)
- **Python GUI**: [visiuun/VMacropad](https://github.com/visiuun/VMacropad)

---

## 4. Technical Constraints & Realistic Limitations

1. **Firmware Keycode Range Limit (`F1–F12` max, no `F13–F24`)**:
   - Inspecting `MINI KeyBoard.exe` (`BasicKeys` / `FunKey` / `MULKey`) shows this CH57x 3-key firmware only supports standard HID keycodes up to `F12` (`0x45`), not `F13–F18` (`0x68–0x6D`). Attempting to flash `F13–F18` produces no key output.
   - **Solution**: `flash_base.py` programs `Ctrl+Shift+Alt+F1..F6` (`modifier = 0x07`, `keycode = 0x3A..0x3F`) and commits flash after each key, while `switcher.py` intercepts that rare modifier+F-key signature and releases the trigger modifiers before sending the target shortcut.
2. **Do Not Flash on Every App Switch (Flash Wear)**:
   - CH57x stores keymaps in internal flash with finite write endurance. `flash_base.py` writes `Ctrl+Shift+Alt+F1..F6` **once**, while `switcher.py` remaps them in software at `0 ms` latency and sends LED updates without committing to flash (`--no-flash` behavior).
2. **Windows UIPI / Administrator Boundary**:
   - When the foreground application runs elevated (Administrator), Windows blocks `WH_KEYBOARD_LL` / `SendInput` from a non-elevated process. Run `python switcher.py` from an elevated terminal if you need switching inside Admin apps.
3. **Windows HID Exclusivity (`MI_00`, `MI_02&COL01`, `MI_03`)**:
   - Windows locks standard Keyboard and Mouse HID collections from direct `CreateFileW` reads. Use `WH_KEYBOARD_LL` (as in `key_tester.py` / `switcher.py`) or Windows Raw Input API instead.
4. **Firmware Sub-variant Differences**:
   - Other `0x1189:0x8890` hardware batches (`k884x` vs `k8850`) may use different packet headers (`0x03`, `0xFE`, `0xFD`). Always verify with `--dry-run` before flashing unfamiliar hardware.
5. **USB Connection Required for Config**:
   - `MI_01` configuration requires a wired USB connection (not Bluetooth).
6. **PowerShell Paths Containing `[` or `]`**:
   - Brackets in Windows folder names are parsed as wildcards by `Get-ChildItem -Path`; always pass `-LiteralPath` in PowerShell scripts.
7. **Firmware Binary Backup Not Supported Over USB HID**:
   - The stock CH57x `MI_01` HID protocol only supports writing keymaps/LEDs (`WriteDevice`); there is **no command to read back the firmware binary or internal flash** over USB HID, and factory WCH chips typically enable Flash Read Protection (CRP) against ISP/bootloader readout.
   - **What can be backed up**: Hardware descriptors & protocol spec are saved in [device_spec.json](file:///g:/ws/microKeyboard/config/device_spec.json) and this `README.md`, alongside the original vendor software (`MINI KeyBoard.exe`).
8. **No Runtime Layer Switching Over USB HID (`0xA1` is Flash-Only)**:
   - Verified on real hardware: `0xA1 <layer> 0x00` (`Send_SwLayer`) only selects which layer slot is written during `Download_Click` / flashing. It **does not** switch the active runtime layer while using the keyboard; runtime layer switching requires a physical Layer button on the board (if equipped).

---

## 5. Project Layout (`v1.1.1`)

```text
microKeyboard/
├── README.md                  # Hardware, protocol & usage reference
├── scripts/
│   └── create_shortcuts.ps1       # Creates Windows .lnk shortcuts on any PC
├── assets/
│   ├── microkeyboard.ico          # Switcher application & tray icon
│   └── microkeyboard_flasher.ico  # Hardware Flasher application icon
├── config/
│   ├── profiles.json              # Per-app Switcher keymap & LED profiles
│   ├── hardware_layers.json       # Local record of Hardware Layers 1..3
│   └── device_spec.json           # Captured USB/HID hardware descriptors
├── docs/
│   └── KEYMAP.md                  # Full keymap table (Layer 1 Standalone + Layer 3 Switcher)
├── microkeyboard/                 # Core Python package (__version__ = "1.1.0")
│   ├── hid_transport.py           # Win32 ctypes Raw HID transport (MI_01)
│   ├── protocol.py                # 64-byte HID packet builders
│   ├── led.py                     # LED mode & layer CLI
│   ├── flash_base.py              # CLI Dual-Layer programmer
│   ├── flash_gui.py               # Standalone Hardware Flasher GUI (Layers 1..3 + LED)
│   ├── switcher.py                # Real-time per-app keymap & LED switcher
│   ├── window_enum.py             # Win32 running window/app enumerator
│   ├── tray_and_lock.py           # Single-instance mutex & System Tray icon
│   ├── gui.py                     # Tkinter Switcher & LED editor GUI
│   └── key_tester.py              # Live WH_KEYBOARD_LL key/knob monitor
└── tests/
    └── test_microkeyboard.py  # Unit tests
```

See [KEYMAP.md](file:///g:/ws/microKeyboard/docs/KEYMAP.md) for the complete keymap & LED mode table.

---

## 6. Usage

0. **Create Windows Shortcuts (Optional, One-Time)**
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcuts.ps1
   ```
   Creates `microKeyboard GUI.lnk`, `microKeyboard Tray.lnk`, and `microKeyboard Flasher.lnk` in the project root (ignored by Git).

0a. **Launch Switcher GUI (`v1.1.1`)**
   - Double-click `microKeyboard GUI.lnk` (normal window) or `microKeyboard Tray.lnk` (starts minimized in System Tray with Switcher active), or run:
     ```powershell
     python -m microkeyboard.gui
     python -m microkeyboard.gui --minimized
     ```
   - Features: edit `config/profiles.json`, **Pick App...** from running windows, **Capture 3s** (with topmost countdown popup & full-title capture), **Rec** / **Preset** key input (click again to cancel), **Test LED**, **Start/Stop Switcher** with live hardware log, **Exit**, minimize/close to **System Tray**, and single-instance protection.

0b. **Launch Hardware Flasher GUI (Layers 1..3)**
   - Double-click `microKeyboard Flasher.lnk` or run:
     ```powershell
     python -m microkeyboard.flash_gui
     ```
   - Configure and flash **Layer 1 (Standalone)**, **Layer 2**, or **Layer 3 (Switcher)** and persistent RGB LED mode without cluttering the daily Switcher app.

1. **Test / Change RGB LED Mode & Layer**
   ```powershell
   python -m microkeyboard.led --mode 2             # Set LED mode 0, 1, or 2 and save to flash
   python -m microkeyboard.led --mode 1 --no-flash  # Preview LED mode without writing flash
   python -m microkeyboard.led --layer 1            # Switch active hardware layer (1..3)
   ```

2. **Program Hardware Keymap (`python -m microkeyboard.flash_base`)**
   ```powershell
   python -m microkeyboard.flash_base --dry-run                 # Inspect 64-byte payloads
   python -m microkeyboard.flash_base                           # Flash Switcher base (Ctrl+Shift+Alt+F1..F6) to Layer 1
   python -m microkeyboard.flash_base --preset standalone-l1    # Flash Standalone (Left, Play/Pause, Right, Vol-/+/Mute) to Layer 1
   python -m microkeyboard.flash_base --preset dual             # Flash Layer 3 (Switcher) + Layer 1 (Standalone)
   ```

3. **Monitor Incoming Keys / Knob Events**
   ```powershell
   python -m microkeyboard.key_tester               # Press Ctrl+C to stop
   python -m microkeyboard.key_tester --seconds 10  # Auto-stop after 10 seconds
   ```

4. **Run Real-Time Per-App Switcher (CLI)**
   ```powershell
   python -m microkeyboard.switcher                 # Uses config/profiles.json
   python -m microkeyboard.switcher --no-led        # Disable MI_01 LED sync on app switch
   pythonw -m microkeyboard.switcher                # Silent background CLI (no console window)
   ```

5. **Run Unit Tests**
   ```powershell
   python -m unittest discover -s tests -v
   ```

---

## 7. Backlog & Future Considerations

- **[Done in `v1.1.1`] Standalone `.exe` Packaging (PyInstaller `--onedir`)**:
  - Built via `scripts/build_exe.ps1` into `microKeyboard.exe` (Switcher + System Tray) and `microKeyboardFlasher.exe` (Hardware Flasher), packaged as `microKeyboard-v1.1.1-win64.zip` on GitHub Releases.
  - Note: Native `pythonw.exe` + `.lnk` shortcuts remain available for fastest startup and zero Antivirus false-positive risk on machines with Python installed.
- **[R&D] Custom CH552G Firmware Exploration**:
  - *References*: `biemster/3keys_1knob`, `eccherda/ch552g_mini_keyboard` (QMK/ZMK are not supported on 8-bit CH552G).
  - *Constraint*: Requires opening the case to short bootloader pads, verifying batch GPIO pinouts, and accepting irreversible overwrite of stock firmware (no USB HID backup).

---

## 8. License

This project is licensed under the [MIT License](LICENSE).
