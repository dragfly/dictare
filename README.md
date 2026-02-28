# dictare

Voice-first control for AI coding agents.

Speak to control Claude Code, Cursor, Aider, or any CLI tool — privately, on your hardware.

## Features

- **Voice-to-Agent** — voice commands drive your AI coding agent, not just text
- **Single command** — `dictare agent claude` and you're talking to Claude Code
- **100% local** — Whisper STT runs on-device, zero data leaves your machine
- **Multi-agent** — switch agents with your voice: *"agent cursor"*
- **Open protocol** — [OpenVIP](spec/) lets any tool connect via SSE
- **Bidirectional** — STT (voice in) + TTS (voice out)

## Install

**macOS** (recommended):

```bash
git clone https://github.com/dragfly/dictare && cd dictare
./scripts/macos-install.sh
```

**Linux / pip**:

```bash
pip install dictare
```

## Quick Start

```bash
# 1. Install as system service (starts at login, like Ollama)
dictare service install

# 2. Launch your agent
dictare agent claude
```

Speak and Claude Code executes. That's it.

## How It Works

```
  Microphone
      |
      v
 ┌─────────────────────┐
 │  Whisper STT         │  (local, on-device)
 └──────────┬───────────┘
            v
 ┌─────────────────────┐
 │  Pipeline            │  filters: submit detection,
 │  (filters + executor)│  agent switching, enrichment
 └──────────┬───────────┘
            v
 ┌─────────────────────┐
 │  OpenVIP HTTP/SSE    │  open protocol
 └──────────┬───────────┘
            v
 ┌─────────────────────┐
 │  Agent               │  Claude Code, Cursor, Aider, ...
 └─────────────────────┘
```

The **engine** runs as a system service (launchd on macOS, systemd on Linux).
It preloads STT models so there's zero cold-start when you speak.
Agents connect via SSE — each in its own terminal.

## Agent Templates

Define agents in `~/.config/dictare/config.toml`:

```toml
[agent_types.claude]
command = ["claude"]
description = "Claude Code"

[agent_types.aider]
command = ["aider", "--model", "claude-3-opus"]
description = "Aider with Opus"
```

Then launch with a single command:

```bash
dictare agent claude                          # uses template
dictare agent claude -- claude --model opus   # override command
```

## Voice Commands

| Voice command | Action |
|---|---|
| *"invia"* / *"send"* / *"submit"* | Submit text to the agent (Enter) |
| *"agent claude"* / *"agent cursor"* | Switch to a different agent |

Submit triggers are multilingual (en, it, es, de, fr) and configurable in config.

## Service Management

```bash
dictare service install     # Install + enable + start (auto-start at login)
dictare service status      # Check service and engine status
dictare service stop        # Stop the service
dictare service uninstall   # Remove the service
dictare service logs        # View recent logs
```

## Keyboard Mode

Don't need an agent? Use dictare as a pure dictation tool — voice to keystrokes.
Set output mode to `keyboard` in config:

```bash
dictare config set output.mode keyboard
```

**Hotkey** to toggle listening (configurable):
- macOS: **Right ⌥** (Right Option) by default
- Linux: **Scroll Lock** by default

Change it in Settings → Keyboard, or:

```bash
dictare config set hotkey.key KEY_RIGHTMETA   # Right ⌘
```

## Text-to-Speech

```bash
dictare speak "Hello world"
dictare speak --engine piper "Hello"
echo "Hello" | dictare speak
```

Engines: `espeak`, `say` (macOS), `piper`, `kokoro`, `outetts`, `coqui`

## Configuration

```bash
dictare config edit           # Open config in editor
dictare config list           # Show all settings
dictare config get stt.model
dictare config set stt.language it
```

## Requirements

- **Python 3.11**
- **macOS** or **Linux**

**macOS**: Grant **Input Monitoring** permission when prompted during `dictare service install`.
System Settings > Privacy & Security > Input Monitoring > enable Dictare.

**Linux**: Join input group: `sudo usermod -aG input $USER` (log out/in).

## Development

```bash
git clone https://github.com/dragfly/dictare && cd dictare

# macOS Apple Silicon (MLX GPU acceleration)
uv sync --python 3.11 --extra mlx

# macOS Intel / Linux
uv sync --python 3.11

# Run engine in foreground
uv run --python 3.11 dictare serve

# Tests
uv run --python 3.11 pytest tests/ -x

# Tests (parallel)
uv run --python 3.11 pytest tests/ -x -n auto
```

> Ghostty users: add `keybind = shift+enter=text:\n` to config. See [TERMINAL_COMPATIBILITY.md](TERMINAL_COMPATIBILITY.md).

## License

MIT
