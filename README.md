# voxtype

Voice-to-text for your terminal. Speak into your microphone and have your words typed anywhere.

**Linux-first** | Push-to-talk or VAD | Wake word support | Works with any app

## Features

- **Push-to-talk**: Hold a key, speak, release → text appears
- **VAD mode**: Hands-free, automatic speech detection
- **Wake word**: Say "Hey voxtype" to start listening
- **Universal**: Works with any terminal, editor, browser (via ydotool/wtype)
- **Offline**: Local Whisper model, no cloud required
- **Fast**: ~2 second latency with base model

## Quick Start (Linux)

```bash
git clone https://github.com/dragfly/voxtype
cd voxtype
./install.sh              # No sudo, builds via Docker
./setup-permissions.sh    # One-time sudo
# Log out and back in
systemctl --user start ydotoold
uv run voxtype run
```

Hold **ScrollLock**, speak, release. Text appears where your cursor is.

### GPU Acceleration (Optional)

For faster transcription with large models, install with CUDA support:

```bash
./install.sh --gpu        # Installs nvidia-cudnn-cu12
```

Then run with `--gpu`:

```bash
uv run voxtype run --gpu --model large-v3
```

Requires NVIDIA GPU with CUDA 12+ drivers installed.

## Quick Start (macOS)

```bash
git clone https://github.com/dragfly/voxtype
cd voxtype
./install-macos.sh        # For Apple Silicon: ./install-macos.sh --mlx
# Grant Accessibility permissions (see installer output)
uv run voxtype run --key KEY_RIGHTMETA
```

Hold **Right Command (⌘)**, speak, release. Text appears where your cursor is.

### MLX Acceleration (Apple Silicon)

For faster transcription on M1/M2/M3 Macs:

```bash
./install-macos.sh --mlx  # Installs mlx-whisper
huggingface-cli login     # Required: MLX models are hosted on Hugging Face
```

Create a free token at https://huggingface.co/settings/tokens

Then run with `--mlx`:

```bash
uv run voxtype run --mlx --model large-v3-turbo --key KEY_RIGHTMETA
```

MLX uses the Metal GPU, significantly faster than CPU.

> **Note**: Linux with `faster-whisper` doesn't require Hugging Face login.

## Usage

```bash
voxtype run                       # Push-to-talk mode
voxtype run --vad                 # VAD mode (hands-free)
voxtype run --vad --wake-word Hey # Wake word mode
voxtype run --model medium        # Larger model, better accuracy
voxtype run --language it         # Force Italian
voxtype run --enter               # Auto-press Enter after typing
voxtype run --clipboard           # Use clipboard (for accented chars)
voxtype check                     # Verify setup
voxtype speak "Hello world"       # Text-to-speech (requires espeak-ng)
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--vad` | | Voice Activity Detection (hands-free) |
| `--wake-word` | `-w` | Trigger phrase (e.g., "Joshua") |
| `--model` | `-m` | Whisper model (tiny/base/small/medium/large-v3/large-v3-turbo) |
| `--language` | `-l` | Language code (it, en, es, fr...) or "auto" |
| `--key` | `-k` | Push-to-talk key (KEY_SCROLLLOCK, KEY_RIGHTMETA, etc.) |
| `--enter` | `-e` | Auto-press Enter after typing |
| `--clipboard` | `-C` | Copy to clipboard instead of typing |
| `--keyboard` | `-K` | Force keyboard typing (may crash some apps) |
| `--gpu` | | Use GPU acceleration (NVIDIA CUDA) |
| `--mlx` | | Use GPU acceleration (Apple Silicon Metal) |
| `--config` | `-c` | Path to custom config file |
| `--max-duration` | `-d` | Max recording duration in seconds (default 60) |
| `--silence-ms` | `-s` | VAD silence duration to end speech (default 1200) |
| `--typing-delay` | | Delay between keystrokes in ms (for keyboard mode) |
| `--log-file` | `-L` | JSONL log file for structured logging |
| `--debug` | | Show all transcriptions (debug mode) |
| `--no-commands` | | Disable voice command processing |
| `--verbose` | `-v` | Enable verbose output |

## Configuration

```bash
voxtype init    # Create ~/.config/voxtype/config.toml
voxtype config  # Show current config
```

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
