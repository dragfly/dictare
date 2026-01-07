"""Keyboard shortcuts input source."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass

from voxtype.input.base import InputCallback, InputEvent, InputSource

@dataclass
class KeyBinding:
    """A keyboard shortcut binding."""

    modifiers: frozenset[str]  # e.g., {"ctrl", "shift"}
    key: str  # e.g., "l", "f1", "space"
    command: str
    args: dict | None = None

class KeyboardShortcutSource(InputSource):
    """Listens for keyboard shortcuts with modifiers.

    Shortcuts on the default keyboard MUST have at least one modifier
    (Ctrl, Alt, Cmd/Meta, Shift) to avoid conflicts with normal typing.
    """

    MODIFIER_MAP = {
        "ctrl": {"ctrl", "control", "ctrl_l", "ctrl_r"},
        "alt": {"alt", "option", "alt_l", "alt_r", "alt_gr"},
        "shift": {"shift", "shift_l", "shift_r"},
        "meta": {"cmd", "command", "meta", "super", "cmd_l", "cmd_r", "super_l", "super_r"},
    }

    def __init__(self, bindings: list[KeyBinding]) -> None:
        """Initialize with keyboard bindings.

        Args:
            bindings: List of keyboard bindings to listen for.

        Raises:
            ValueError: If any binding lacks modifiers.
        """
        for binding in bindings:
            if not binding.modifiers:
                raise ValueError(
                    f"Keyboard binding for '{binding.command}' must have at least one modifier"
                )
        self._bindings = bindings
        self._running = False
        self._listener = None
        self._on_input: InputCallback | None = None
        self._current_modifiers: set[str] = set()

    def start(self, on_input: InputCallback) -> bool:
        """Start listening for keyboard shortcuts."""
        self._on_input = on_input

        if sys.platform == "darwin":
            return self._start_pynput()
        else:
            # Linux - try pynput for X11, evdev would need different approach
            return self._start_pynput()

    def _start_pynput(self) -> bool:
        """Start using pynput."""
        try:
            from pynput import keyboard
        except ImportError:
            return False

        def on_press(key):
            mod = self._key_to_modifier(key)
            if mod:
                self._current_modifiers.add(mod)
            else:
                key_name = self._key_to_name(key)
                if key_name:
                    self._check_bindings(key_name)

        def on_release(key):
            mod = self._key_to_modifier(key)
            if mod:
                self._current_modifiers.discard(mod)

        # Note: suppress=False allows shortcuts to also reach focused apps, but is much safer
        # (suppress=True caused complete keyboard freeze if callbacks blocked)
        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()
        self._running = True
        return True

    def _key_to_modifier(self, key) -> str | None:
        """Convert pynput key to canonical modifier name."""
        try:
            from pynput.keyboard import Key

            key_name = key.name if hasattr(key, "name") else str(key)

            for canonical, variants in self.MODIFIER_MAP.items():
                if key_name.lower() in variants:
                    return canonical
        except Exception:
            pass
        return None

    def _key_to_name(self, key) -> str | None:
        """Convert pynput key to key name."""
        try:
            if hasattr(key, "char") and key.char:
                return key.char.lower()
            elif hasattr(key, "name"):
                return key.name.lower()
        except Exception:
            pass
        return None

    def _check_bindings(self, key: str) -> None:
        """Check if pressed key + current modifiers match any binding."""
        for binding in self._bindings:
            if key == binding.key.lower() and binding.modifiers == self._current_modifiers:
                event = InputEvent(
                    command=binding.command,
                    args=binding.args or {},
                    source="keyboard",
                )
                if self._on_input:
                    self._on_input(event)
                break

    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._listener:
            self._listener.stop()
            # Wait for listener thread to actually stop (with timeout to avoid hanging)
            try:
                self._listener.join(timeout=2.0)
            except Exception:
                pass
            self._listener = None

    @property
    def source_name(self) -> str:
        return "Keyboard Shortcuts"

    @property
    def is_running(self) -> bool:
        return self._running

    @staticmethod
    def parse_shortcut(shortcut: str) -> tuple[frozenset[str], str]:
        """Parse shortcut string like 'Ctrl+Shift+L' into modifiers and key.

        Returns:
            Tuple of (frozenset of canonical modifiers, key name)
        """
        parts = [p.strip().lower() for p in shortcut.split("+")]
        key = parts[-1]
        modifiers = set()

        for mod in parts[:-1]:
            if mod in ("ctrl", "control"):
                modifiers.add("ctrl")
            elif mod in ("alt", "option"):
                modifiers.add("alt")
            elif mod in ("shift",):
                modifiers.add("shift")
            elif mod in ("cmd", "command", "meta", "super"):
                modifiers.add("meta")

        return frozenset(modifiers), key
