"""Keyboard shortcut configuration - simple text-based UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from voxtype.config import get_config_path, load_config

def _capture_shortcut() -> str | None:
    """Capture a shortcut using pynput. Returns shortcut string or None if cancelled."""
    try:
        from pynput import keyboard
    except ImportError:
        return None

    modifiers: set[str] = set()
    result: list[str | None] = [None]  # Use list to allow modification in nested function

    def on_press(key):
        # Escape cancels
        if key == keyboard.Key.esc:
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
        elif modifiers:
            # Regular key with modifiers - capture it
            if hasattr(key, "char") and key.char:
                key_name = key.char.upper()
            elif hasattr(key, "name"):
                key_name = key.name.upper()
            else:
                return None

            result[0] = "+".join(sorted(modifiers)) + "+" + key_name
            return False

        return None

    def on_release(key):
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl):
            modifiers.discard("Ctrl")
        elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt, keyboard.Key.alt_gr):
            modifiers.discard("Alt")
        elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift):
            modifiers.discard("Shift")
        elif key in (keyboard.Key.cmd_l, keyboard.Key.cmd_r, keyboard.Key.cmd):
            modifiers.discard("Cmd")

    print("  Press shortcut (Esc to cancel)...", end="", flush=True)

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

    # Clear the "Press shortcut" line
    print("\r" + " " * 40 + "\r", end="")

    return result[0]

AVAILABLE_COMMANDS: list[dict[str, Any]] = [
    {"command": "project-next", "description": "Switch to next agent", "display": "project-next"},
    {"command": "project-prev", "description": "Switch to previous agent", "display": "project-prev"},
    {"command": "switch-to-project-index", "description": "Switch to agent #1", "args": {"index": 1}, "display": "switch-to-project #1"},
    {"command": "switch-to-project-index", "description": "Switch to agent #2", "args": {"index": 2}, "display": "switch-to-project #2"},
    {"command": "switch-to-project-index", "description": "Switch to agent #3", "args": {"index": 3}, "display": "switch-to-project #3"},
    {"command": "switch-to-project-index", "description": "Switch to agent #4", "args": {"index": 4}, "display": "switch-to-project #4"},
    {"command": "switch-to-project-index", "description": "Switch to agent #5", "args": {"index": 5}, "display": "switch-to-project #5"},
    {"command": "toggle-listening", "description": "Toggle listening on/off", "display": "toggle-listening"},
    {"command": "switch-mode", "description": "Switch transcription/command", "display": "switch-mode"},
    {"command": "repeat", "description": "Repeat last sent text", "display": "repeat"},
    {"command": "discard", "description": "Discard current recording", "display": "discard"},
]

def _command_key(cmd: dict[str, Any]) -> str:
    if cmd.get("args"):
        return f"{cmd['command']}:{cmd['args']}"
    return cmd["command"]

def _get_current_shortcuts(config) -> dict[str, str]:
    shortcuts = {}
    for s in config.keyboard.shortcuts:
        cmd = s.get("command", "")
        keys = s.get("keys", "")
        args = s.get("args", {})
        key = f"{cmd}:{args}" if args else cmd
        shortcuts[key] = keys
    return shortcuts

def _save_shortcuts(shortcuts: dict[str, str], config_path: Path) -> None:
    import toml  # type: ignore[import-untyped]

    config_data = {}
    if config_path.exists():
        with open(config_path) as f:
            config_data = toml.load(f)

    shortcuts_list = []
    for cmd in AVAILABLE_COMMANDS:
        key = _command_key(cmd)
        if key in shortcuts and shortcuts[key]:
            entry: dict[str, Any] = {"keys": shortcuts[key], "command": cmd["command"]}
            if cmd.get("args"):
                entry["args"] = cmd["args"]
            shortcuts_list.append(entry)

    if "keyboard" not in config_data:
        config_data["keyboard"] = {}
    config_data["keyboard"]["shortcuts"] = shortcuts_list

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        toml.dump(config_data, f)

def _normalize_shortcut(s: str) -> str:
    """Normalize shortcut format: Ctrl+Alt+N"""
    parts = [p.strip() for p in s.replace("-", "+").split("+")]
    normalized = []
    for p in parts:
        p_lower = p.lower()
        if p_lower in ("ctrl", "control"):
            normalized.append("Ctrl")
        elif p_lower in ("alt", "option", "opt"):
            normalized.append("Alt")
        elif p_lower in ("shift"):
            normalized.append("Shift")
        elif p_lower in ("cmd", "command", "meta", "super", "win"):
            normalized.append("Cmd")
        else:
            normalized.append(p.upper())
    return "+".join(normalized)

def _print_table(shortcuts: dict[str, str]) -> None:
    """Print the shortcuts table."""
    print("\n  #  Command                   Shortcut")
    print("  " + "─" * 50)
    for i, cmd in enumerate(AVAILABLE_COMMANDS):
        key = _command_key(cmd)
        shortcut = shortcuts.get(key, "") or "─"
        print(f"  {i+1:2} {cmd['display']:<24} {shortcut}")
    print()

def configure_shortcuts() -> None:
    """Simple text-based shortcut configuration."""
    config_path = get_config_path()
    config = load_config(config_path if config_path.exists() else None)
    shortcuts = _get_current_shortcuts(config)

    print("\n╭─ voxtype - Keyboard Shortcuts ─╮")

    while True:
        _print_table(shortcuts)
        print("  Commands: [number] set shortcut, [d number] delete, [s] save, [q] quit")

        try:
            cmd = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return

        if not cmd:
            continue

        if cmd == "q":
            print("  Exited without saving.")
            return

        if cmd == "s":
            _save_shortcuts(shortcuts, config_path)
            print("  ✓ Saved!")
            return

        # Delete: "d 3" or "d3"
        if cmd.startswith("d"):
            try:
                num = int(cmd[1:].strip()) - 1
                if 0 <= num < len(AVAILABLE_COMMANDS):
                    key = _command_key(AVAILABLE_COMMANDS[num])
                    shortcuts.pop(key, None)
                    print(f"  Cleared #{num+1}")
                else:
                    print("  Invalid number")
            except ValueError:
                print("  Usage: d <number>")
            continue

        # Set shortcut: "3" then capture shortcut
        try:
            num = int(cmd) - 1
            if 0 <= num < len(AVAILABLE_COMMANDS):
                command = AVAILABLE_COMMANDS[num]
                key = _command_key(command)
                print(f"\n  Setting: {command['display']}")

                shortcut = _capture_shortcut()

                if shortcut:
                    # Check duplicates
                    for k, v in list(shortcuts.items()):
                        if v == shortcut and k != key:
                            for c in AVAILABLE_COMMANDS:
                                if _command_key(c) == k:
                                    print(f"  (moved from {c['display']})")
                                    break
                            shortcuts.pop(k)
                            break
                    shortcuts[key] = shortcut
                    print(f"  Set: {shortcut}")
                else:
                    print("  Cancelled")
            else:
                print("  Invalid number")
        except ValueError:
            print("  Unknown command")
