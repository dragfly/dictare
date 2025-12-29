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
```

### 2. Build ydotool from Source (Recommended)

The Ubuntu/Debian package is too old. Build from source using Docker:

```bash
cd build
./build-ydotool.sh
sudo mv ydotool ydotoold /usr/local/bin/
```

Start the daemon:
```bash
sudo ydotoold &
# Or create a systemd service (see below)
```

<details>
<summary>Create systemd service for ydotoold</summary>

```bash
sudo tee /etc/systemd/system/ydotoold.service > /dev/null << 'EOF'
[Unit]
Description=ydotool daemon
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ydotoold
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ydotoold
```
</details>

**Alternatives** (if you prefer not to use Docker):
```bash
sudo apt install wtype      # Wayland only
sudo apt install xdotool    # X11 only
```

### 3. Grant Input Device Access

```bash
sudo usermod -aG input $USER
# Log out and back in for the change to take effect
```

### 4. Install claude-mic

```bash
# Clone
git clone https://github.com/dragfly/claude-mic
cd claude-mic

# Install with uv
uv sync

# Build and install evdev (requires Docker, avoids system python3-dev)
./build/build-evdev.sh
uv pip install build/evdev.whl
```

**Alternative**: Install evdev with system python3-dev (installs ~30MB of packages):
```bash
sudo apt install python3-dev
uv pip install evdev
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

Build and install evdev using Docker (no python3-dev needed):
```bash
./build/build-evdev.sh
uv pip install build/evdev.whl
```

Or use pynput on X11:
```bash
pip install python-xlib pynput
```

### "ydotool daemon not running"

If you built from source:
```bash
sudo ydotoold &
```

Or if you created the systemd service:
```bash
sudo systemctl start ydotoold
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
