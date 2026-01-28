# voxtype

Voice-to-text for your terminal. Speak and your words appear.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dragfly/voxtype/main/install.sh | sh
```

Or from source:
```bash
git clone https://github.com/dragfly/voxtype && cd voxtype && ./install.sh
```

## Quick Start

```bash
voxtype listen
```

**Tap hotkey** to toggle listening. **Double-tap** to switch mode.

- macOS: **Command**
- Linux: **ScrollLock**

## Commands

### Voice Input

```bash
voxtype listen                    # Start listening for voice input
voxtype transcribe                # One-shot: record and output text
voxtype execute -- llm "{{text}}" # Record and run command with transcript
```

### Text-to-Speech

```bash
voxtype speak "Hello world"           # Speak text
voxtype speak --engine qwen3 "Hello"  # Use specific TTS engine
echo "Hello" | voxtype speak          # Pipe text to speak
voxtype speak --list-engines          # List available engines
```

Available engines: `espeak`, `say` (macOS), `piper`, `coqui`, `qwen3`, `outetts`

### Daemon (Fast TTS)

Keep models loaded in memory for instant TTS:

```bash
voxtype daemon start      # Start daemon in background
voxtype daemon status     # Show daemon status
voxtype daemon stop       # Stop daemon

# With daemon running, speak is instant:
voxtype speak "Hello"     # Uses daemon (fast)
voxtype speak "Hello" --no-daemon  # Force in-process
```

### Agent Mode

Run commands with voice input via OpenVIP protocol:

```bash
# Terminal 1: Start the agent
voxtype agent claude -- claude

# Terminal 2: Send voice to agent
voxtype listen --agents claude
```

### Configuration

```bash
voxtype init              # Create default config file
voxtype config list       # Show all settings
voxtype config get stt.model_size
voxtype config set stt.language it
voxtype config shortcuts  # Configure keyboard shortcuts
```

### Utilities

```bash
voxtype check             # Verify system setup
voxtype devices           # List input devices
voxtype devices --hid     # List HID devices (for profiles)
voxtype backends          # List device backends
voxtype cmd toggle-listening  # Send command to running instance
```

### Logs

```bash
voxtype log listen        # View listen session logs
voxtype log listen -f     # Follow logs live
voxtype log agent claude  # View agent logs
voxtype log list          # List all log files
```

## Requirements

**macOS**: Grant Accessibility permission for your terminal app:
1. System Settings → Privacy & Security → Accessibility
2. Click **+** and add your terminal (Terminal, iTerm2, etc.)
3. Restart your terminal

**Linux**: The installer sets up everything automatically. If needed:
- Join input group: `sudo usermod -aG input $USER` (then log out/in)
- Start daemon: `systemctl --user start ydotoold`

## Development

```bash
git clone https://github.com/dragfly/voxtype && cd voxtype

# macOS Apple Silicon (with MLX GPU acceleration)
uv sync --python 3.11 --extra mlx
uv run --python 3.11 voxtype listen

# macOS Intel / Linux
uv sync --python 3.11
uv run --python 3.11 voxtype listen
```

> **Note**: Python 3.11 is required for MLX/torch compatibility.

### Ghostty Terminal

If using Ghostty, add to `~/.config/ghostty/config`:
```
keybind = shift+enter=text:\n
```
This fixes Shift+Enter for multi-line input. See [TERMINAL_COMPATIBILITY.md](TERMINAL_COMPATIBILITY.md).

## Help

```bash
voxtype --help            # All commands
voxtype <command> --help  # Command options
```

## License

MIT
