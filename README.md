# voxtype

Voice-first control for AI coding agents.

Speak to control Claude Code, Cursor, Aider, or any CLI tool — privately, on your hardware.

## Features

- **Voice-to-Agent** — voice commands drive your AI coding agent, not just text
- **Single command** — `voxtype agent claude` and you're talking to Claude Code
- **100% local** — Whisper STT runs on-device, zero data leaves your machine
- **Multi-agent** — switch agents with your voice: *"agent cursor"*
- **Open protocol** — [OpenVIP](spec/) lets any tool connect via SSE
- **Bidirectional** — STT (voice in) + TTS (voice out)

## Install

```bash
pip install voxtype
```

Or from source:

```bash
git clone https://github.com/dragfly/voxtype && cd voxtype
uv sync --python 3.11
```

## Quick Start

```bash
# 1. Install as system service (starts at login, like Ollama)
voxtype service install

# 2. Launch your agent
voxtype agent claude
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
 │  Agent (PTY)         │  Claude Code, Cursor, Aider, ...
 └─────────────────────┘
```

The **engine** runs as a system service (launchd on macOS, systemd on Linux).
It preloads STT models so there's zero cold-start when you speak.
Agents connect via SSE — each in its own terminal.

## Agent Templates

Define agents in `~/.config/voxtype/config.toml`:

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
voxtype agent claude                          # uses template
voxtype agent claude -- claude --model opus   # override command
```

## Voice Commands

| Voice command | Action |
|---|---|
| *"invia"* / *"send"* / *"submit"* | Submit text to the agent (Enter) |
| *"agent claude"* / *"agent cursor"* | Switch to a different agent |

Submit triggers are multilingual (en, it, es, de, fr) and configurable in config.

## Service Management

```bash
voxtype service install     # Install + enable + start (auto-start at login)
voxtype service status      # Check service and engine status
voxtype service stop        # Stop the service
voxtype service uninstall   # Remove the service
voxtype service logs        # View recent logs
```

## Engine

For manual control without the system service:

```bash
voxtype engine start -d --agents   # Start engine as daemon
voxtype engine status              # Check engine status
voxtype engine stop                # Stop engine
```

## Keyboard Mode

Don't need an agent? Use voxtype as a pure dictation tool — voice to keystrokes:

```bash
voxtype listen --keyboard
```

**Hotkey** to toggle listening:
- macOS: **Command**
- Linux: **ScrollLock**

## Text-to-Speech

```bash
voxtype speak "Hello world"
voxtype speak --engine qwen3 "Hello"
echo "Hello" | voxtype speak
```

Engines: `espeak`, `say` (macOS), `piper`, `coqui`, `qwen3`, `outetts`

## Configuration

```bash
voxtype config edit           # Open config in editor
voxtype config list           # Show all settings
voxtype config get stt.model
voxtype config set stt.language it
```

## Requirements

- **Python 3.11**
- **macOS** or **Linux**

**macOS**: Grant Accessibility permission for your terminal:
System Settings > Privacy & Security > Accessibility > add your terminal app.

**Linux**: Join input group: `sudo usermod -aG input $USER` (log out/in).

## Development

```bash
git clone https://github.com/dragfly/voxtype && cd voxtype

# macOS Apple Silicon (MLX GPU acceleration)
uv sync --python 3.11 --extra mlx

# macOS Intel / Linux
uv sync --python 3.11

# Run
uv run --python 3.11 voxtype listen --keyboard

# Tests
uv run --python 3.11 python -m pytest tests/ -x

# Tests (parallel — useful when suite grows beyond 10s)
uv run --python 3.11 python -m pytest tests/ -x -n auto
```

> Ghostty users: add `keybind = shift+enter=text:\n` to config. See [TERMINAL_COMPATIBILITY.md](TERMINAL_COMPATIBILITY.md).

## License

MIT
