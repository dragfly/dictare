# voxtype

Voice-to-text for your terminal. Speak into your microphone and have your words typed anywhere.

**Linux-first** | VAD or Push-to-talk | Wake word support | Works with any app

## Features

- **VAD mode** (default): Hands-free, automatic speech detection
- **Push-to-talk**: Hold a key, speak, release → text appears
- **Wake word**: Say "Hey voxtype" to start listening
- **Universal**: Works with any terminal, editor, browser (via ydotool/wtype)
- **Offline**: Local Whisper model, no cloud required
- **Fast**: GPU auto-detected on macOS (MLX) and Linux (CUDA)

## Quick Start

```bash
git clone https://github.com/dragfly/voxtype
cd voxtype
./install.sh              # Auto-detects platform (macOS/Linux)
uv run voxtype run
```

The installer automatically:
- **macOS**: Detects Apple Silicon → enables MLX GPU acceleration
- **Linux**: Builds ydotool via Docker, sets up systemd service

### macOS

After install, grant Accessibility permissions (see installer output), then:

```bash
uv run voxtype run
```

Hold **Right Command (⌘)** to toggle listening. MLX is auto-detected on Apple Silicon.

### Linux

After install, run permissions setup and start the daemon:

```bash
./setup-permissions.sh    # One-time sudo
# Log out and back in
systemctl --user start ydotoold
uv run voxtype run
```

Hold **ScrollLock** to toggle listening. CUDA GPU is auto-detected.

### GPU Acceleration

- **macOS (Apple Silicon)**: MLX is auto-detected, no flags needed
- **Linux (NVIDIA)**: CUDA is auto-detected if available

## Usage

```bash
voxtype run                       # VAD mode (default, hands-free)
voxtype run --ptt                 # Push-to-talk mode
voxtype run --wake-word Hey       # Wake word mode
voxtype run --model medium        # Larger model, better accuracy
voxtype run --language it         # Force Italian
voxtype run --no-enter            # Don't auto-press Enter after typing
voxtype run --clipboard           # Use clipboard (for accented chars)
voxtype check                     # Verify setup
voxtype speak "Hello world"       # Text-to-speech (requires espeak-ng)
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--ptt` | | Push-to-talk mode (VAD is default) |
| `--wake-word` | `-w` | Trigger phrase (e.g., "Joshua") |
| `--model` | `-m` | Whisper model (tiny/base/small/medium/large-v3/large-v3-turbo) |
| `--language` | `-l` | Language code (it, en, es, fr...) or "auto" |
| `--key` | `-k` | Push-to-talk key (KEY_SCROLLLOCK, KEY_RIGHTMETA, etc.) |
| `--no-enter` | | Don't auto-press Enter after typing |
| `--clipboard` | `-C` | Copy to clipboard instead of typing |
| `--keyboard` | `-K` | Force keyboard typing (may crash some apps) |
| `--gpu` | `-g` | Force GPU acceleration (NVIDIA CUDA) |
| `--mlx` | | Force GPU acceleration (Apple Silicon Metal) |
| `--config` | `-c` | Path to custom config file |
| `--max-duration` | `-d` | Max recording duration in seconds (default 60) |
| `--silence-ms` | `-s` | VAD silence duration to end speech (default 1200) |
| `--typing-delay` | | Delay between keystrokes in ms (for keyboard mode) |
| `--log-file` | `-L` | JSONL log file for structured logging |
| `--debug` | | Show all transcriptions (debug mode) |
| `--no-commands` | | Disable voice command processing |
| `--ollama-model` | `-O` | Ollama model for commands (default: qwen2.5:1.5b) |
| `--verbose` | `-v` | Enable verbose output |

## Configuration

```bash
voxtype init                              # Create ~/.config/voxtype/config.toml
voxtype config                            # Show all config with env var names
voxtype config get stt.model_size         # Get a single value
voxtype config set stt.model_size large-v3  # Set a value
voxtype config path                       # Show config file path
```

### Environment Variables

All config options can be overridden via environment variables:

```bash
VOXTYPE_STT_MODEL_SIZE=large-v3 voxtype run
VOXTYPE_STT_LANGUAGE=it voxtype run
VOXTYPE_COMMAND_OLLAMA_MODEL=qwen2.5:3b voxtype run
```

Priority (highest to lowest):
1. CLI flags (`--model`, `--language`, etc.)
2. Environment variables (`VOXTYPE_*`)
3. Config file (`~/.config/voxtype/config.toml`)
4. Built-in defaults

## Requirements

- Linux (X11 or Wayland) or macOS (Intel or Apple Silicon)
- Docker (for building dependencies on Linux)
- [uv](https://github.com/astral-sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## How It Works

```
Audio → Whisper (STT) → LLM (commands) → ydotool (typing)
```

1. **Audio capture**: sounddevice records from your microphone
2. **Speech-to-text**: faster-whisper transcribes locally
3. **Command processing**: Ollama LLM interprets commands (with keyword fallback)
4. **Text injection**: ydotool/wtype types text into the active window

### Text Injection Modes

voxtype can inject text in two ways:

| Mode | How it works | Pros | Cons |
|------|--------------|------|------|
| **Clipboard** (default) | Copy to clipboard, simulate Ctrl+V | Fast, reliable, handles unicode | Overwrites clipboard |
| **Keyboard** (`--keyboard`) | Simulate each keystroke | Doesn't touch clipboard | Slower, may crash some apps |

On Linux, both modes use **ydotool** - a virtual keyboard that sends input via `/dev/uinput`. The `ydotoold` daemon must be running:

```bash
systemctl --user start ydotoold   # Start now
systemctl --user enable ydotoold  # Auto-start on login
```

On macOS, text injection uses **osascript** (AppleScript) which requires Accessibility permissions.

## Platform Notes

### macOS

- **Clipboard mode is default**: voxtype uses clipboard (paste) instead of keystroke injection. This avoids compatibility issues with some apps. Use `--keyboard` to force direct typing.
- **Accessibility permissions**: Required for both clipboard paste and keystroke simulation. Add your terminal app in System Settings → Privacy & Security → Accessibility.
- **Latency**: Expect ~8 seconds with `large-v3-turbo` on MLX. Use `medium` or `small` for faster response.

### Linux

- **Clipboard mode is default**: Same as macOS, clipboard is preferred for compatibility. Use `--keyboard` to force direct typing via ydotool/wtype/xdotool.
- **GPU acceleration**: With CUDA, expect ~2-3 seconds latency with `large-v3`.

## License

MIT
