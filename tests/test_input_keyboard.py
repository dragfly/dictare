"""Tests for input/keyboard.py — KeyBinding, KeyboardShortcutSource, parse_shortcut."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dictare.input.base import InputEvent
from dictare.input.keyboard import KeyBinding, KeyboardShortcutSource


class TestKeyBinding:
    def test_creation(self) -> None:
        binding = KeyBinding(
            modifiers=frozenset({"ctrl"}),
            key="l",
            command="toggle-listening",
        )
        assert binding.key == "l"
        assert binding.command == "toggle-listening"
        assert "ctrl" in binding.modifiers
        assert binding.args is None

    def test_with_args(self) -> None:
        binding = KeyBinding(
            modifiers=frozenset({"ctrl"}),
            key="1",
            command="switch-to-project-index",
            args={"index": 1},
        )
        assert binding.args == {"index": 1}


class TestParseShortcut:
    def test_single_modifier(self) -> None:
        mods, key = KeyboardShortcutSource.parse_shortcut("Ctrl+L")
        assert mods == frozenset({"ctrl"})
        assert key == "l"

    def test_multi_modifier(self) -> None:
        mods, key = KeyboardShortcutSource.parse_shortcut("Ctrl+Shift+A")
        assert mods == frozenset({"ctrl", "shift"})
        assert key == "a"

    def test_cmd_alias(self) -> None:
        mods, key = KeyboardShortcutSource.parse_shortcut("Cmd+K")
        assert mods == frozenset({"meta"})
        assert key == "k"

    def test_command_alias(self) -> None:
        mods, key = KeyboardShortcutSource.parse_shortcut("Command+X")
        assert mods == frozenset({"meta"})
        assert key == "x"

    def test_alt_option(self) -> None:
        mods, key = KeyboardShortcutSource.parse_shortcut("Option+N")
        assert mods == frozenset({"alt"})
        assert key == "n"

    def test_super_alias(self) -> None:
        mods, key = KeyboardShortcutSource.parse_shortcut("Super+Space")
        assert mods == frozenset({"meta"})
        assert key == "space"


class TestKeyboardShortcutSourceInit:
    def test_rejects_bindings_without_modifiers(self) -> None:
        binding = KeyBinding(modifiers=frozenset(), key="l", command="test")
        with pytest.raises(ValueError, match="must have at least one modifier"):
            KeyboardShortcutSource([binding])

    def test_accepts_bindings_with_modifiers(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])
        assert src.is_running is False

    def test_source_name(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])
        assert src.source_name == "Keyboard Shortcuts"


class TestKeyboardCheckBindings:
    def test_matching_binding_fires_callback(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="toggle-listening")
        src = KeyboardShortcutSource([binding])
        events = []
        src._on_input = lambda e: events.append(e)
        src._current_modifiers = {"ctrl"}

        src._check_bindings("l")
        assert len(events) == 1
        assert events[0].command == "toggle-listening"
        assert events[0].source == "keyboard"

    def test_non_matching_modifiers_no_fire(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl", "shift"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])
        events = []
        src._on_input = lambda e: events.append(e)
        src._current_modifiers = {"ctrl"}  # Missing shift

        src._check_bindings("l")
        assert len(events) == 0

    def test_non_matching_key_no_fire(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])
        events = []
        src._on_input = lambda e: events.append(e)
        src._current_modifiers = {"ctrl"}

        src._check_bindings("k")
        assert len(events) == 0

    def test_binding_with_args(self) -> None:
        binding = KeyBinding(
            modifiers=frozenset({"ctrl"}),
            key="1",
            command="switch",
            args={"index": 1},
        )
        src = KeyboardShortcutSource([binding])
        events = []
        src._on_input = lambda e: events.append(e)
        src._current_modifiers = {"ctrl"}

        src._check_bindings("1")
        assert events[0].args == {"index": 1}


class TestKeyboardModifierMapping:
    def test_key_to_modifier_ctrl(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])

        mock_key = MagicMock()
        mock_key.name = "ctrl_l"
        assert src._key_to_modifier(mock_key) == "ctrl"

    def test_key_to_modifier_alt(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])

        mock_key = MagicMock()
        mock_key.name = "alt"
        assert src._key_to_modifier(mock_key) == "alt"

    def test_key_to_modifier_not_modifier(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])

        mock_key = MagicMock()
        mock_key.name = "a"
        assert src._key_to_modifier(mock_key) is None

    def test_key_to_name_char(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])

        mock_key = MagicMock()
        mock_key.char = "L"
        assert src._key_to_name(mock_key) == "l"

    def test_key_to_name_named(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])

        mock_key = MagicMock(spec=[])  # no char attribute
        mock_key.name = "F1"
        assert src._key_to_name(mock_key) == "f1"


class TestKeyboardStop:
    def test_stop_clears_state(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])
        src._running = True
        src._listener = MagicMock()
        src.stop()
        assert src.is_running is False
        assert src._listener is None

    def test_stop_without_listener(self) -> None:
        binding = KeyBinding(modifiers=frozenset({"ctrl"}), key="l", command="test")
        src = KeyboardShortcutSource([binding])
        src.stop()  # Should not raise
