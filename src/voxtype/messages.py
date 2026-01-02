"""User-facing messages for voxtype.

Centralizes important messages for consistency and easier modification.
Use .format() for templates with placeholders.
"""

# Hotkey / Device messages
HOTKEY_DEVICE_SELECTED = "[hotkey] Using device: {path} ({name})"
HOTKEY_NOT_AVAILABLE = "Hotkey not available: {error}"
HOTKEY_KEY_NOT_FOUND = "Key {key} not found, using {fallback} instead"
HOTKEY_NO_DEVICE = """No keyboard device found.
Please add your user to the 'input' group:
  sudo usermod -aG input $USER
Then log out and back in."""

# Audio messages
AUDIO_DEVICE_RECONNECTING = "Audio device changed, reconnecting..."
AUDIO_RECONNECT_FAILED = "Could not reconnect audio. Please restart."
AUDIO_RECONNECT_OK = "OK ({name})"

# STT messages
STT_LOADING = "Loading STT model {model} on {device} (first run may download)..."
STT_DEVICE_FALLBACK = "Actually using: {device}"

# VAD messages
VAD_LOADING = "Loading VAD model (first run may download)..."
VAD_MAX_DURATION = "Max duration ({seconds}s) - sending, still listening..."
VAD_TOO_SHORT = "Too short, ignoring."
VAD_NO_SPEECH = "No speech detected."

# Listening state messages
LISTENING_ON = ">>> LISTENING ON"
LISTENING_OFF = "<<< LISTENING OFF"
LISTENING_MODE = "({mode} mode)"
NOT_LISTENING = "Not listening, ignoring."

# Mode switch messages
MODE_TRANSCRIPTION = ">>> MODE: TRANSCRIPTION (fast)"
MODE_COMMAND = ">>> MODE: COMMAND (LLM)"

# Transcription messages
TRANSCRIBED = "Transcribed: {text}"
TRANSCRIBING = "Transcribing..."
TRANSCRIBING_QUEUED = "Transcribing (queued)..."

# Injection messages
INJECT_FAILED = "Failed to inject text"
INJECT_SENT = "Sent"
INJECT_SEND_FAILED = "Send failed"

# Controller messages
CONTROLLER_FOUND = "Controller: {device}"
CONTROLLER_NOT_FOUND = "Controller device not found: {device}"
CONTROLLER_EVDEV_MISSING = "evdev not installed, controller disabled"
CONTROLLER_AGENT = ">>> Agent: {agent}"

# LLM messages
LLM_OLLAMA = "LLM processor: ollama ({model})"
LLM_FALLBACK = "LLM processor: keyword fallback"

# Command messages
CMD_REPEAT = "Command: repeat"
CMD_NOTHING_TO_REPEAT = "Nothing to repeat"

# Config validation messages
CONFIG_INVALID_VALUE = "Invalid value '{value}' for {key}. Valid options: {options}"
CONFIG_SET_OK = "Set {key} = {value}"

# Startup messages
READY = "Ready! Start speaking..."
READY_WITH_HOTKEY = "Ready! Start speaking... (or press {key})"
INITIALIZING_VAD = "Initializing VAD components..."
INITIALIZING = "Initializing components..."
SHUTTING_DOWN = "Shutting down..."

# Dependency check messages
CHECK_TITLE = "Checking dependencies..."
CHECK_ALL_OK = "All required dependencies are available!"
CHECK_MISSING = "Some required dependencies are missing."
CHECK_TO_FIX = "To fix, run:"
CHECK_HW_ACCEL = "To enable hardware acceleration:"

# Error messages
ERROR_GENERIC = "Error: {error}"
ERROR_YDOTOOLD = """ERROR: ydotoold is not running

ydotoold is required for text injection on Linux.
It handles keyboard simulation for both typing and clipboard paste.

To start it:
  systemctl --user start ydotoold

To enable auto-start on login:
  systemctl --user enable ydotoold"""
