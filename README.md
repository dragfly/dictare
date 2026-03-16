<div align="center">

<img src="assets/icon.svg" width="80" height="80" alt="dictare icon">

# DICTA**re**

**Voice layer for AI coding agents.**

Speak to your agent. No window focus required. 100% local.

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/dragfly/dictare/actions/workflows/ci.yml/badge.svg)](https://github.com/dragfly/dictare/actions)

[dictare.io](https://dictare.io) · [OpenVIP Protocol](https://openvip.dev)

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
- **Open protocol** — [OpenVIP](https://openvip.dev) — any tool can implement the SSE endpoint
- **Bidirectional** — STT (voice in) + TTS (voice out)

## Install

**macOS** — [full guide](https://dictare.io/docs/installation/)

```bash
brew install dragfly/tap/dictare
```

**Linux** — [full guide](https://dictare.io/docs/installation/)

```bash
curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash
sudo usermod -aG input $USER   # required for hotkey (log out/in after)
```

### Permissions

> **macOS** — grant when prompted:
> 1. **Microphone** — prompted on first launch
> 2. **Input Monitoring** — System Settings → Privacy & Security → enable Dictare
> 3. **Accessibility** — needed for keyboard mode (typing into other apps)
>
> After granting all three: `dictare service restart`

> **Linux** — two steps:
> 1. **Input group** (hotkey, X11 + Wayland): `sudo usermod -aG input $USER` — log out/in
> 2. **ydotool** (keyboard mode on Wayland): `sudo apt install ydotool`

## Quick Start

```bash
dictare agent freddie       # starts the default profile (Claude Code)
```

That's it. The service starts automatically. Speak — your agent receives the transcription.

If you prefer a different coding agent:

```bash
dictare agent ozzy --profile codex      # OpenAI Codex
dictare agent gilmour --profile gemini  # Google Gemini CLI
dictare agent bowie --profile aider     # Aider
```

## How It Works

```
  Microphone
      │
      ▼
  STT Module       Whisper (MLX / CTranslate2) or Parakeet (ONNX)
      │             all local, zero cold-start
      ▼
  Pipeline         submit detection, mute control, agent switching
      │
      ▼
  OpenVIP          HTTP / SSE — open protocol
      │
      ▼
  Agent            receives transcription, no window focus needed
```

The engine runs as a background service (launchd on macOS, systemd on Linux).
STT models are preloaded at startup. Each agent connects in its own terminal.

## Agent Profiles

Profiles are predefined in `~/.config/dictare/config.toml`:

```toml
[agent_profiles]
default = "claude"

[agent_profiles.claude]
command = ["claude"]
description = "Claude Code"

[agent_profiles.codex]
command = ["codex"]
description = "OpenAI Codex"

[agent_profiles.pi]
command = ["pi", "--provider", "ollama", "--model", "qwen3:8b"]
continue_args = ["-c"]
description = "Pi + Ollama local, agentic with tools"
```

Then connect:

```bash
dictare agent freddie                      # default profile (claude)
dictare agent ozzy --profile codex         # use codex profile
dictare agent -- claude --model opus       # explicit command override
```

## Voice Commands

| Say | Action |
|---|---|
| *"ok, submit"* / *"ok, send"* / *"ok, invia"* / *"ja, senden"* | Submit to agent (Enter) |
| *"ok, mute"* / *"ok, hold on"* | Mute (stop listening) |
| *"ok, listen"* / *"ok, listen up"* | Unmute (resume listening) |
| *"agent coding"* / *"agent review"* | Switch active agent |

Submit triggers are multilingual (en, de, es, it, fr) and fully configurable.

## Hotkey Cheat Sheet

Default hotkey: **Right ⌘** (macOS) / **Scroll Lock** (Linux).

| Gesture | Action |
|---------|--------|
| **Single tap** | Toggle listening on/off |
| **Double tap** | Submit (send Enter to agent) |
| **Right Alt + hotkey** | Switch mode: agents ↔ keyboard |

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

Full configuration reference at [dictare.io/docs/configuration](https://dictare.io/docs/configuration/).

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

dictare is the reference implementation of [OpenVIP](https://openvip.dev) — an open protocol for
voice input to AI agents. Any tool can implement the SSE endpoint and receive
voice transcriptions from dictare.

## License

MIT
