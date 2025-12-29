# claude-mic

Voice-to-text for Claude Code CLI. Speak into your microphone and have your words typed into Claude Code.

## Features

- **Push-to-talk**: Hold a key while speaking, release to transcribe
- **Offline STT**: Uses faster-whisper (Whisper-based) for high-quality local transcription
- **Auto-typing**: Automatically types transcribed text into the active terminal
- **Multi-language**: Supports 99+ languages with auto-detection
- **Cross-platform**: Linux (primary), macOS (secondary)

## Quick Start (Linux)

### 1. Install System Dependencies

```bash
# Audio library
sudo apt install libportaudio2

# Python headers (for evdev compilation)
sudo apt install python3-dev

# Text injection - install ONE of these:
sudo apt install ydotool    # Recommended (X11/Wayland/console)
# OR
sudo apt install wtype      # Wayland only
# OR
sudo apt install xdotool    # X11 only
```

### 2. Start ydotool Daemon (if using ydotool)

```bash
sudo systemctl enable --now ydotoold
```

### 3. Grant Input Device Access

```bash
sudo usermod -aG input $USER
# Log out and back in for the change to take effect
```

### 4. Install claude-mic

```bash
# With uv (recommended)
git clone https://github.com/dragfly/claude-mic
cd claude-mic
uv sync --extra linux   # Creates venv and installs deps including evdev

# Or with pip
pip install claude-mic
```

### 5. Verify Setup

```bash
uv run claude-mic check
# Or if using pip: claude-mic check
```

You should see all components as `OK` or `OPTIONAL`.

### 6. Run

```bash
uv run claude-mic run
```

Hold **ScrollLock**, speak, release. Text appears in your terminal.

## Usage

```bash
uv run claude-mic run              # Start push-to-talk mode
uv run claude-mic run -v           # Verbose mode
uv run claude-mic run --model small    # Use larger model (more accurate)
uv run claude-mic run --language it    # Force Italian

uv run claude-mic check            # Verify dependencies
uv run claude-mic init             # Create config file
uv run claude-mic config           # Show current config
```

> **Note**: If you installed with `pip install claude-mic` globally, you can omit `uv run`.

## Configuration

Config file: `~/.config/claude-mic/config.toml`

```toml
[stt]
backend = "faster-whisper"
model_size = "base"        # tiny, base, small, medium, large-v3
language = "auto"          # auto-detect, or "en", "it", etc.

[hotkey]
key = "KEY_SCROLLLOCK"     # evdev key name

[injection]
backend = "auto"           # ydotool, wtype, xdotool, clipboard
fallback_to_clipboard = true

[audio]
sample_rate = 16000
device = null              # null = default microphone
```

### Model Sizes

| Model | Size | Latency | Accuracy |
|-------|------|---------|----------|
| tiny | ~75MB | ~1-2s | Good |
| base | ~150MB | ~2-3s | Better |
| small | ~500MB | ~4-5s | Best for most use |
| medium | ~1.5GB | ~6-8s | High accuracy |
| large-v3 | ~3GB | ~10s+ | Maximum accuracy |

## Troubleshooting

### "No hotkey backend available"

Install evdev (requires python3-dev):
```bash
sudo apt install python3-dev
pip install evdev
```

Or use pynput on X11:
```bash
pip install python-xlib pynput
```

### "ydotool daemon not running"

```bash
sudo systemctl start ydotoold
sudo systemctl enable ydotoold  # Auto-start on boot
```

### "Cannot access input devices"

```bash
sudo usermod -aG input $USER
# Then log out and back in
```

### Text goes to clipboard instead of typing

No auto-typing tool detected. Install ydotool, wtype, or xdotool (see Quick Start).

### ScrollLock key not working

Your keyboard may not have ScrollLock. Edit config to use another key:
```toml
[hotkey]
key = "KEY_F12"  # or KEY_PAUSE, KEY_RIGHTMETA, etc.
```

## How It Works

1. **Hotkey press** → Start recording audio
2. **Hotkey release** → Stop recording
3. **Transcription** → faster-whisper converts speech to text
4. **Injection** → ydotool/wtype types text into active window

```
IDLE → RECORDING → TRANSCRIBING → INJECTING → IDLE
```

## License

MIT
