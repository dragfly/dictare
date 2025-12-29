# claude-mic

Voice-to-text for Claude Code CLI. Speak into your microphone and have your words typed into the terminal.

## Quick Start

### Linux

```bash
git clone https://github.com/dragfly/claude-mic
cd claude-mic
./install.sh              # No sudo, builds via Docker
./setup-permissions.sh    # One-time sudo
# Log out and back in
systemctl --user start ydotoold
uv run claude-mic run
```

### macOS

```bash
git clone https://github.com/dragfly/claude-mic
cd claude-mic
./install-macos.sh
# Grant Accessibility permissions (see installer output)
uv run claude-mic run
```

Hold **ScrollLock** (or **F13**), speak, release. Text appears in your terminal.

## Requirements

**Linux:**
- Docker (for building dependencies)
- [uv](https://github.com/astral-sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

**macOS:**
- [Homebrew](https://brew.sh) (for portaudio)
- [uv](https://github.com/astral-sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Accessibility permissions for Terminal

## What Does `setup-permissions.sh` Do?

```bash
sudo apt-get install -y libportaudio2 xclip  # Audio + clipboard
sudo usermod -aG input $USER                  # Access to input devices
# + udev rule for /dev/uinput (ydotool needs this)
```

Separate script so you can review it easily.

## Usage

```bash
uv run claude-mic run                  # Start push-to-talk
uv run claude-mic run --model small    # Larger model, more accurate
uv run claude-mic run --language it    # Force Italian
uv run claude-mic run --enter          # Auto-press Enter after typing
uv run claude-mic check                # Verify setup
```

## Configuration

```bash
uv run claude-mic init    # Create ~/.config/claude-mic/config.toml
uv run claude-mic config  # Show current config
```

Example `~/.config/claude-mic/config.toml`:
```toml
[stt]
model_size = "medium"    # Better accuracy (see table below)
language = "it"          # Force Italian (or "auto" to detect)

[injection]
auto_enter = true        # Press Enter after typing

[hotkey]
key = "KEY_SCROLLLOCK"   # Change push-to-talk key
```

### Models

| Model | Size | Latency | Quality |
|-------|------|---------|---------|
| tiny | ~75MB | ~1s | Good |
| base | ~150MB | ~2s | Better (default) |
| small | ~500MB | ~4s | Best for most |
| large-v3 | ~3GB | ~10s | Maximum |

## System-wide Install

```bash
./install.sh --system     # Requires sudo
```

## Uninstall

```bash
./uninstall.sh            # User install
./uninstall.sh --system   # System-wide
```

## License

MIT
