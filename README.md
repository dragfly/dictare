<div align="center">

<svg width="64" height="64" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="100" height="100" rx="22" fill="#6d5ce6"/>
  <g transform="translate(0, 4)">
    <rect x="35" y="12" width="30" height="48" rx="15" fill="none" stroke="#FFFFFF" stroke-width="6"/>
    <path d="M 30 46 A 20 26 0 0 0 70 46" stroke="#FFFFFF" stroke-width="6" fill="none" stroke-linecap="round"/>
    <line x1="50" y1="72" x2="50" y2="82" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round"/>
    <line x1="38" y1="82" x2="62" y2="82" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round"/>
  </g>
</svg>

# DICTA**re**

**Voice layer for AI coding agents.**

Speak to your agent. No window focus required. 100% local.

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://python.org)
[![CI](https://github.com/dragfly/dictare/actions/workflows/ci.yml/badge.svg)](https://github.com/dragfly/dictare/actions)

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
- **Open protocol** — [OpenVIP](spec/) — any tool can implement the SSE endpoint
- **Bidirectional** — STT (voice in) + TTS (voice out)

## Install

**macOS:**

```bash
git clone https://github.com/dragfly/dictare && cd dictare
./scripts/macos-install.sh
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
dictare agent coding
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

Define agents in `~/.config/dictare/config.toml`:

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

Then connect:

```bash
dictare agent coding                              # uses template
dictare agent coding -- claude --model opus       # override command
```

## Voice Commands

| Say | Action |
|---|---|
| *"submit"* / *"send"* / *"invia"* / *"senden"* | Submit to agent (Enter) |
| *"agent coding"* / *"agent review"* | Switch active agent |

Submit triggers are multilingual (en, it, es, de, fr) and fully configurable.

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

## Roadmap

- **Plugin architecture**: pipeline filters loadable as plugins, each declaring its model dependencies (STT, TTS, LLM, Vision).
- **Realtime partial transcription**: stream partial results while speaking using a fast small model.
- **Cloud relay** (Phase 2): E2E encrypted relay connecting web clients to local engines.

## Protocol

dictare is the reference implementation of [OpenVIP](spec/) — an open protocol for
voice input to AI agents. Any tool can implement the SSE endpoint and receive
voice transcriptions from dictare.

## License

MIT
