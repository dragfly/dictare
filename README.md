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

## Run

```bash
voxtype listen
```

**Tap hotkey** to toggle listening. **Double-tap** to switch mode.

- macOS: **⌘ Command**
- Linux: **ScrollLock**

## Requirements

**macOS**: Grant Accessibility permission for your terminal app:
1. System Settings → Privacy & Security → Accessibility
2. Click **+** and add your terminal (Terminal, iTerm2, etc.)
3. Restart your terminal

**Linux**: The installer sets up everything automatically. If needed:
- Join input group: `sudo usermod -aG input $USER` (then log out/in)
- Start daemon: `systemctl --user start ydotoold`

## More

```bash
voxtype --help              # All commands
voxtype listen --help          # All options
voxtype check               # Verify setup
voxtype devices             # List input devices
```

See [docs/](docs/) for device profiles, configuration, and advanced usage.

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

> **Note**: Python 3.11 is required for MLX/torch compatibility. Always use `--python 3.11` explicitly with ALL uv commands (sync, run, etc.).

### Ghostty Terminal

If using Ghostty, add to `~/.config/ghostty/config`:
```
keybind = shift+enter=text:\n
```
This fixes Shift+Enter for multi-line input. See [TERMINAL_COMPATIBILITY.md](TERMINAL_COMPATIBILITY.md) for details.

## License

MIT
