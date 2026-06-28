"""Tests for filtering terminal-side global hotkey sequences."""

from __future__ import annotations

from dictare.agent.mux import (
    _strip_terminal_sequences,
    _terminal_sequences_for_evdev_key,
)


class TestTerminalSequencesForEvdevKey:
    """Configured global hotkeys map to their terminal escape sequences."""

    def test_scroll_lock_kitty_sequence(self) -> None:
        sequences = _terminal_sequences_for_evdev_key("KEY_SCROLLLOCK")
        assert b"\x1b[57359u" in sequences
        assert b"\x1b[57359;1:3u" in sequences

    def test_function_key_above_f12_kitty_sequence(self) -> None:
        sequences = _terminal_sequences_for_evdev_key("KEY_F18")
        assert b"\x1b[57381u" in sequences
        assert b"\x1b[57359u" not in sequences

    def test_function_key_accepts_short_name(self) -> None:
        sequences = _terminal_sequences_for_evdev_key("F18")
        assert b"\x1b[57381u" in sequences

    def test_f12_legacy_sequence(self) -> None:
        sequences = _terminal_sequences_for_evdev_key("KEY_F12")
        assert b"\x1b[24~" in sequences
        assert b"\x1b[24;2~" in sequences

    def test_right_alt_kitty_sequence(self) -> None:
        sequences = _terminal_sequences_for_evdev_key("KEY_RIGHTALT")
        assert b"\x1b[57449u" in sequences

    def test_unknown_key_has_no_sequences(self) -> None:
        assert _terminal_sequences_for_evdev_key("KEY_UNKNOWNKEY") == []


class TestStripTerminalSequences:
    """Only configured hotkey sequences are stripped."""

    def test_strips_configured_scroll_lock_sequence(self) -> None:
        sequences = _terminal_sequences_for_evdev_key("KEY_SCROLLLOCK")
        cleaned, found = _strip_terminal_sequences(b"hello\x1b[57359uworld", sequences)
        assert found is True
        assert cleaned == b"helloworld"

    def test_strips_configured_event_variant(self) -> None:
        sequences = _terminal_sequences_for_evdev_key("KEY_SCROLLLOCK")
        cleaned, found = _strip_terminal_sequences(b"\x1b[57359;9:3u", sequences)
        assert found is True
        assert cleaned == b""

    def test_does_not_strip_different_key_sequence(self) -> None:
        sequences = _terminal_sequences_for_evdev_key("KEY_SCROLLLOCK")
        original = b"\x1b[57381u"
        cleaned, found = _strip_terminal_sequences(original, sequences)
        assert found is False
        assert cleaned == original
