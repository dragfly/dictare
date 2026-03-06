<div align="center">

<img src="assets/icon.svg" width="80" height="80" alt="dictare icon">

# DICTA**re**

**Voice layer for AI coding agents.**

Speak to your agent. No window focus required. 100% local.

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://python.org)
[![CI](https://github.com/dragfly/dictare/actions/workflows/ci.yml/badge.svg)](https://github.com/dragfly/dictare/actions)

[dictare.io](https://dictare.io) · [OpenVIP Protocol](https://github.com/openvip-dev/protocol)

</div>

---

## Why dictare

Most voice tools (Wispr Flow, Superwhisper, etc.) simulate keystrokes — they type into
whatever window has focus. Switch to your browser and your code gets your voice.

Dictare uses a protocol. Your agent listens via SSE and receives transcriptions **regardless
of window focus**. Your coding agent can be behind 3 other windows — it still gets your words.

## Features

- **No focus required** — agent receives voice even when its window is in the background
- **Agent-native** — transcriptions go to the agent protocol, not a text field
- **100% local** — STT runs on-device, zero data leaves your machine
- **Multi-agent** — switch agents by voice: *"agent coding"*, *"agent review"*
- **Open protocol** — [OpenVIP](https://github.com/openvip-dev/protocol) — any tool can implement the SSE endpoint
- **Bidirectional** — STT (voice in) + TTS (voice out)

## Install

**macOS:**

```bash
git clone https://github.com/dragfly/dictare && cd dictare
./scripts/install.sh
```

**Linux:**

```bash
pip install dictare
```

## Quick Start

```bash
# 1. Install as system service (auto-starts at login)
dictare service install

# 2. Connect your agent
dictare agent myproject --type coding
```

The service starts automatically. Speak — your agent receives the transcription.

## How It Works

```
  Microphone
      │
      ▼
  STT Module       Whisper (MLX / CTranslate2) or Parakeet (ONNX)
      │             all local, zero cold-start
      ▼
  Pipeline         submit detection, agent switching, language filter
      │
      ▼
  OpenVIP          HTTP / SSE — open protocol
      │
      ▼
  Agent            receives transcription, no window focus needed
```

The engine runs as a background service (launchd on macOS, systemd on Linux).
STT models are preloaded at startup. Each agent connects in its own terminal.

## Agent Templates

Define agent types in `~/.config/dictare/config.toml`:

```toml
[agent_types.coding]
command = ["claude"]
description = "AI coding assistant"

[agent_types.review]
command = ["aider", "--model", "claude-sonnet-4-6"]
description = "Code review"

[agent_types.writing]
command = ["claude", "--model", "claude-opus-4-6"]
description = "Writing and documentation"
```

Then connect using `--type`:

```bash
dictare agent myproject --type coding     # session "myproject", type "coding"
dictare agent frontend --type review      # session "frontend", type "review"
dictare agent -- claude --model opus      # explicit command override
```

## Voice Commands

| Say | Action |
|---|---|
| *"ok, submit"* / *"ok, send"* / *"ok, invia"* / *"ja, senden"* | Submit to agent (Enter) |
| *"agent coding"* / *"agent review"* | Switch active agent type |

Submit triggers are multilingual (en, it, es, de, fr) and fully configurable.

## Hotkey Cheat Sheet

Default hotkey: **Right ⌘** (macOS) / **Scroll Lock** (Linux).

| Gesture | Action |
|---------|--------|
| **Single tap** | Toggle listening on/off |
| **Double tap** | Submit (send Enter to agent) |
| **Long press** (≥0.8s) | Switch mode: agents ↔ keyboard |

## Service Management

```bash
dictare service install     # Install + enable (auto-starts at login)
dictare service start       # Start the service
dictare service stop        # Stop the service
dictare service restart     # Restart the service
dictare service status      # Show service and engine status
dictare service logs        # View recent logs
dictare service uninstall   # Remove the service
```

## Keyboard Mode

No agent? Use dictare as a dictation tool — voice to keystrokes in any app.

```bash
dictare config set output.mode keyboard
```

**Hotkey** to toggle listening (configurable):
- macOS: **Right ⌘** by default
- Linux: **Scroll Lock** by default

```bash
dictare config set hotkey.key KEY_RIGHTALT   # change hotkey
```

## Text-to-Speech

```bash
dictare speak "Hello world"
dictare speak --engine piper "Hello"
echo "Hello" | dictare speak
```

Engines: `espeak`, `say` (macOS), `piper`, `kokoro`

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
System Settings → Privacy & Security → Input Monitoring → enable Dictare.

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

## Protocol

dictare is the reference implementation of [OpenVIP](https://github.com/openvip-dev/protocol) — an open protocol for
voice input to AI agents. Any tool can implement the SSE endpoint and receive
voice transcriptions from dictare.

## License

MIT
