"""Tests for terminal focus event stripping in the agent multiplexer."""

from __future__ import annotations

from dictare.agent.mux import _strip_focus_events

class TestStripFocusEvents:
    """Tests for _strip_focus_events()."""

    def test_no_focus_events(self) -> None:
        """Data without focus events is returned unchanged."""
        data = b"hello world"
        cleaned, focused = _strip_focus_events(data)
        assert cleaned == b"hello world"
        assert focused is None

    def test_focus_in_only(self) -> None:
        """Focus-in sequence is stripped, focused=True."""
        data = b"\x1b[I"
        cleaned, focused = _strip_focus_events(data)
        assert cleaned == b""
        assert focused is True

    def test_focus_out_only(self) -> None:
        """Focus-out sequence is stripped, focused=False."""
        data = b"\x1b[O"
        cleaned, focused = _strip_focus_events(data)
        assert cleaned == b""
        assert focused is False

    def test_focus_in_with_surrounding_data(self) -> None:
        """Focus events are stripped but regular data is preserved."""
        data = b"abc\x1b[Idef"
        cleaned, focused = _strip_focus_events(data)
        assert cleaned == b"abcdef"
        assert focused is True

    def test_focus_out_with_surrounding_data(self) -> None:
        data = b"abc\x1b[Odef"
        cleaned, focused = _strip_focus_events(data)
        assert cleaned == b"abcdef"
        assert focused is False

    def test_both_focus_events_last_wins(self) -> None:
        """When both focus-in and focus-out appear, last one determines state."""
        # Focus-in then focus-out → focused=False
        data = b"\x1b[I\x1b[O"
        cleaned, focused = _strip_focus_events(data)
        assert cleaned == b""
        assert focused is False

        # Focus-out then focus-in → focused=True
        data = b"\x1b[O\x1b[I"
        cleaned, focused = _strip_focus_events(data)
        assert cleaned == b""
        assert focused is True

    def test_mixed_with_keystrokes(self) -> None:
        """Focus events mixed with keystrokes — events stripped, keystrokes kept."""
        data = b"a\x1b[Ib\x1b[Oc"
        cleaned, focused = _strip_focus_events(data)
        assert cleaned == b"abc"
        assert focused is False  # last was focus-out

    def test_empty_data(self) -> None:
        """Empty input returns empty output, focused=None."""
        data = b""
        cleaned, focused = _strip_focus_events(data)
        assert cleaned == b""
        assert focused is None
