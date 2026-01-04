"""Interactive keyboard shortcut configuration UI."""

from __future__ import annotations

import sys
import termios
import tty
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from voxtype.config import get_config_path, load_config

# Commands available for keyboard shortcuts
AVAILABLE_COMMANDS = [
    {
        "command": "project-next",
        "description": "Switch to next agent/project",
        "category": "Navigation",
    },
    {
        "command": "project-prev",
        "description": "Switch to previous agent/project",
        "category": "Navigation",
    },
    {
        "command": "switch-to-project-index",
        "description": "Switch to agent #1",
        "category": "Navigation",
        "args": {"index": 1},
        "display": "switch-to-project #1",
    },
    {
        "command": "switch-to-project-index",
        "description": "Switch to agent #2",
        "category": "Navigation",
        "args": {"index": 2},
        "display": "switch-to-project #2",
    },
    {
        "command": "switch-to-project-index",
        "description": "Switch to agent #3",
        "category": "Navigation",
        "args": {"index": 3},
        "display": "switch-to-project #3",
    },
    {
        "command": "switch-to-project-index",
        "description": "Switch to agent #4",
        "category": "Navigation",
        "args": {"index": 4},
        "display": "switch-to-project #4",
    },
    {
        "command": "switch-to-project-index",
        "description": "Switch to agent #5",
        "category": "Navigation",
        "args": {"index": 5},
        "display": "switch-to-project #5",
    },
    {
        "command": "toggle-listening",
        "description": "Toggle listening on/off",
        "category": "Control",
    },
    {
        "command": "switch-mode",
        "description": "Switch between transcription/command mode",
        "category": "Control",
    },
    {
        "command": "repeat",
        "description": "Repeat last sent text",
        "category": "Text",
    },
    {
        "command": "discard",
        "description": "Discard current recording",
        "category": "Text",
    },
]

def _capture_shortcut(console: Console) -> str | None:
    """Capture a keyboard shortcut from the user.

    Returns:
        Shortcut string like "Ctrl+Alt+N" or None if cancelled.
    """
    console.print("\n[bold cyan]Press your shortcut combination...[/]")
    console.print("[dim](Press Escape to cancel, Backspace to clear)[/]\n")

    try:
        from pynput import keyboard
    except ImportError:
        console.print("[red]Error: pynput not installed[/]")
        return None

    modifiers: set[str] = set()
    key_pressed: str | None = None
    cancelled = False
    clear = False

    def on_press(key):
        nonlocal modifiers, key_pressed, cancelled, clear

        # Check for escape
        if key == keyboard.Key.esc:
            cancelled = True
            return False

        # Check for backspace (clear)
        if key == keyboard.Key.backspace:
            clear = True
            return False

        # Track modifiers
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl):
            modifiers.add("Ctrl")
        elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt, keyboard.Key.alt_gr):
            modifiers.add("Alt")
        elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift):
            modifiers.add("Shift")
        elif key in (keyboard.Key.cmd_l, keyboard.Key.cmd_r, keyboard.Key.cmd):
            modifiers.add("Cmd")
        else:
            # Regular key pressed
            if hasattr(key, "char") and key.char:
                key_pressed = key.char.upper()
            elif hasattr(key, "name"):
                key_pressed = key.name.upper()

            # Only accept if at least one modifier is held
            if modifiers and key_pressed:
                return False

    # Use pynput listener
    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()

    if cancelled:
        console.print("[yellow]Cancelled[/]")
        return None

    if clear:
        console.print("[yellow]Cleared[/]")
        return ""

    if not modifiers:
        console.print("[red]Shortcut must include at least one modifier (Ctrl, Alt, Shift, Cmd)[/]")
        return None

    # Build shortcut string
    parts = sorted(modifiers) + [key_pressed]
    shortcut = "+".join(parts)
    console.print(f"[green]Captured: {shortcut}[/]")
    return shortcut

def _get_current_shortcuts(config) -> dict[str, str]:
    """Get current shortcuts from config as command -> keys mapping."""
    shortcuts = {}
    for s in config.keyboard.shortcuts:
        cmd = s.get("command", "")
        keys = s.get("keys", "")
        args = s.get("args", {})

        # Create unique key for commands with args
        if args:
            key = f"{cmd}:{args}"
        else:
            key = cmd
        shortcuts[key] = keys

    return shortcuts

def _command_key(cmd: dict) -> str:
    """Get unique key for a command (including args)."""
    if cmd.get("args"):
        return f"{cmd['command']}:{cmd['args']}"
    return cmd["command"]

def _save_shortcuts(shortcuts: dict[str, str], config_path: Path) -> bool:
    """Save shortcuts to config file."""
    import toml

    # Read existing config
    if config_path.exists():
        with open(config_path) as f:
            config_data = toml.load(f)
    else:
        config_data = {}

    # Build shortcuts list
    shortcuts_list = []
    for cmd in AVAILABLE_COMMANDS:
        key = _command_key(cmd)
        if key in shortcuts and shortcuts[key]:
            entry: dict[str, Any] = {
                "keys": shortcuts[key],
                "command": cmd["command"],
            }
            if cmd.get("args"):
                entry["args"] = cmd["args"]
            shortcuts_list.append(entry)

    # Update config
    if "keyboard" not in config_data:
        config_data["keyboard"] = {}
    config_data["keyboard"]["shortcuts"] = shortcuts_list

    # Write back
    with open(config_path, "w") as f:
        toml.dump(config_data, f)

    return True

def configure_shortcuts() -> None:
    """Interactive UI for configuring keyboard shortcuts."""
    console = Console()

    # Load current config
    config_path = get_config_path()
    config = load_config(config_path if config_path.exists() else None)
    current_shortcuts = _get_current_shortcuts(config)

    console.print(Panel(
        "[bold]Keyboard Shortcut Configuration[/]\n\n"
        "Configure global keyboard shortcuts for voxtype commands.\n"
        "Shortcuts work system-wide while voxtype is running.\n\n"
        "[dim]Use arrow keys to navigate, Enter to set shortcut, Q to quit[/]",
        title="voxtype",
        border_style="cyan",
    ))

    selected_idx = 0

    while True:
        # Build and display table
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="dim", width=3)
        table.add_column("Command", style="cyan")
        table.add_column("Description")
        table.add_column("Shortcut", style="green")

        for i, cmd in enumerate(AVAILABLE_COMMANDS):
            key = _command_key(cmd)
            shortcut = current_shortcuts.get(key, "")
            display_name = cmd.get("display", cmd["command"])

            prefix = "[bold]> " if i == selected_idx else "  "
            suffix = "[/]" if i == selected_idx else ""

            table.add_row(
                f"{prefix}{i + 1}{suffix}",
                f"{prefix}{display_name}{suffix}",
                f"{prefix}{cmd['description']}{suffix}",
                f"{prefix}{shortcut or '[dim]not set[/]'}{suffix}",
            )

        console.print(table)
        console.print("\n[dim]↑/↓: navigate | Enter: set shortcut | Backspace: clear | Q: save & quit[/]\n")

        # Get key input
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)

            # Handle escape sequences (arrow keys)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":  # Up
                        selected_idx = max(0, selected_idx - 1)
                    elif ch3 == "B":  # Down
                        selected_idx = min(len(AVAILABLE_COMMANDS) - 1, selected_idx + 1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        # Clear screen for redraw
        console.clear()

        # Handle other keys
        if ch == "q" or ch == "Q":
            # Save and quit
            if _save_shortcuts(current_shortcuts, config_path):
                console.print("[green]Shortcuts saved![/]")
            break
        elif ch == "\r" or ch == "\n":  # Enter
            cmd = AVAILABLE_COMMANDS[selected_idx]
            key = _command_key(cmd)
            display_name = cmd.get("display", cmd["command"])
            console.print(f"\nSetting shortcut for: [cyan]{display_name}[/]")

            shortcut = _capture_shortcut(console)
            if shortcut is not None:
                if shortcut == "":
                    current_shortcuts.pop(key, None)
                else:
                    current_shortcuts[key] = shortcut
        elif ch == "\x7f":  # Backspace
            cmd = AVAILABLE_COMMANDS[selected_idx]
            key = _command_key(cmd)
            current_shortcuts.pop(key, None)
            console.print("[yellow]Shortcut cleared[/]")
