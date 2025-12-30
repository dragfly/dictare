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
voxtype run
```

Hold **ScrollLock**, speak, release. Text appears where your cursor is.

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
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--vad` | | Voice Activity Detection (hands-free) |
| `--wake-word` | `-w` | Trigger phrase (e.g., "Hey") |
| `--model` | `-m` | Whisper model (tiny/base/small/medium/large-v3) |
| `--language` | `-l` | Language code (it, en, es, fr...) or "auto" |
| `--key` | `-k` | Push-to-talk key (KEY_SCROLLLOCK, KEY_F5, etc.) |
| `--enter` | `-e` | Auto-press Enter after typing |
| `--clipboard` | `-C` | Copy to clipboard instead of typing |

## Configuration

```bash
voxtype init    # Create ~/.config/voxtype/config.toml
voxtype config  # Show current config
```

## Requirements

- Linux (X11 or Wayland)
- Docker (for building dependencies)
- [uv](https://github.com/astral-sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## How It Works

```
Audio → Whisper (STT) → LLM (commands) → ydotool (typing)
```

1. **Audio capture**: sounddevice records from your microphone
2. **Speech-to-text**: faster-whisper transcribes locally
3. **Command processing**: Ollama LLM interprets commands (with keyword fallback)
4. **Text injection**: ydotool/wtype types text into the active window

## License

MIT
