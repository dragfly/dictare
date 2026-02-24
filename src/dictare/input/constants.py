"""Constants for input handling."""

# HID usage codes to key names mapping (common presenter remote keys)
HID_KEY_MAP = {
    # Keyboard page (0x07)
    0x29: "KEY_ESC",
    0x3E: "KEY_F5",
    0x05: "KEY_B",
    0x13: "KEY_P",
    0x16: "KEY_S",
    0x4B: "KEY_PAGEUP",
    0x4E: "KEY_PAGEDOWN",
    0x52: "KEY_UP",
    0x51: "KEY_DOWN",
    0x50: "KEY_LEFT",
    0x4F: "KEY_RIGHT",
    0x28: "KEY_ENTER",
    0x2C: "KEY_SPACE",
    # Consumer page keys (media controls)
    0xB5: "KEY_NEXTSONG",
    0xB6: "KEY_PREVIOUSSONG",
    0xCD: "KEY_PLAYPAUSE",
    0xE9: "KEY_VOLUMEUP",
    0xEA: "KEY_VOLUMEDOWN",
    0xE2: "KEY_MUTE",
}
