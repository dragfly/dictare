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

### Core Requirements (both platforms)

| Dependency | Install | Purpose |
|------------|---------|---------|
| **Python 3.11+** | System/pyenv | Runtime |
| **uv** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Package manager |
| **Ollama** (optional) | [ollama.ai](https://ollama.ai) | Voice command processing |

### macOS Dependencies

| Dependency | Install | Purpose | Required? |
|------------|---------|---------|-----------|
| **Accessibility** | System Settings → Privacy | Keyboard simulation | ✅ Yes |
| **hidapi** | Auto-installed | Device profiles | Auto |
| **Karabiner-Elements** | `brew install --cask karabiner-elements` | Device grab (presenter remotes) | Optional |
| **MLX** | `uv pip install mlx mlx-whisper` | GPU acceleration (Apple Silicon) | Recommended |

### Linux Dependencies

| Dependency | Install | Purpose | Required? |
|------------|---------|---------|-----------|
| **Docker** | [docker.com](https://docker.com) | Build ydotool | ✅ Yes (first install) |
| **ydotool** | `./install.sh` builds it | Text injection | ✅ Yes |
| **evdev** | Auto-installed | Hotkey & device profiles | Auto |
| **input group** | `sudo usermod -aG input $USER` | Device access | ✅ Yes |
| **CUDA** | NVIDIA driver | GPU acceleration | Recommended |

### Optional: Voice Commands with Ollama

For intelligent voice command processing:

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a small, fast model
ollama pull qwen2.5:1.5b

# voxtype will auto-detect Ollama
voxtype run
```

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

## Device Profiles (Presenter Remotes, Macro Pads)

Use dedicated input devices like presenter remotes or macro pads to control voxtype.

### List Connected Devices

```bash
voxtype devices          # List HID devices with vendor/product IDs
voxtype backends         # Show available input backends
```

### Create a Device Profile

Create `~/.config/voxtype/devices/<name>.toml`:

```toml
# ~/.config/voxtype/devices/presenter.toml
vendor_id = 0x1234      # From "voxtype devices" output
product_id = 0x5678

[bindings]
KEY_PAGEUP = "project-prev"
KEY_PAGEDOWN = "project-next"
KEY_B = "toggle-listening"
KEY_ESC = "submit"
```

### Available Commands

| Command | Description |
|---------|-------------|
| `toggle-listening` | Start/stop listening |
| `listening-on` | Start listening |
| `listening-off` | Stop listening |
| `toggle-mode` | Switch transcription/command mode |
| `project-next` | Next agent (multi-output mode) |
| `project-prev` | Previous agent |
| `submit` | Press Enter |
| `discard` | Discard current buffer |
| `repeat` | Repeat last transcription |

You can also send commands externally via Unix socket:

```bash
voxtype cmd toggle-listening    # Send command to running voxtype
```

### Device Input Backends

voxtype uses different backends for device input depending on platform:

| Backend | Platform | Device Grab | Description |
|---------|----------|-------------|-------------|
| **evdev** | Linux | ✅ Yes | Native Linux input, exclusive device access |
| **hidapi** | macOS/Linux | ❌ No | Cross-platform HID, keys pass through to other apps |
| **karabiner** | macOS | ✅ Yes | Uses Karabiner-Elements for exclusive grab |

Check available backends:
```bash
voxtype backends
```

### Karabiner-Elements Setup (macOS)

For exclusive device grab on macOS (prevents keys from reaching other apps):

1. Install Karabiner-Elements:
   ```bash
   brew install --cask karabiner-elements
   ```

2. Open Karabiner-Elements and grant required permissions

3. Run voxtype with your device profile - it auto-generates Karabiner config:
   ```bash
   uv run voxtype run --verbose
   ```

4. In Karabiner-Elements preferences:
   - Go to "Complex Modifications"
   - Click "Add rule"
   - Enable "voxtype presenter controls"

5. Your presenter remote now works exclusively with voxtype!

### Platform Support

- **Linux**: Uses evdev backend with exclusive device grab
- **macOS (with Karabiner)**: Uses karabiner backend with exclusive device grab
- **macOS (without Karabiner)**: Uses hidapi backend (no grab, keys pass through)

## Platform Notes

### macOS

- **Keyboard mode is default**: Uses Quartz for direct Unicode keystroke injection
- **Accessibility permissions**: Required for keyboard simulation. Add your terminal app in System Settings → Privacy & Security → Accessibility
- **Fallback**: If Quartz unavailable, falls back to osascript → clipboard
- Use `--clipboard` to force clipboard mode (overwrites clipboard but more compatible)

### Linux

- **Keyboard mode is default**: Uses ydotool for universal keystroke injection (X11/Wayland/TTY)
- **Fallback**: ydotool → wtype → xdotool → clipboard
- **GPU acceleration**: CUDA auto-detected, expect ~2-3 seconds latency with `large-v3-turbo`

## License

MIT
