"""Tests for configurable claim key in PTY stdin reader."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dictare.agent.mux import (
    _CTRL_BACKSLASH,
    _CTRL_BACKSLASH_CSI_U,
    _claim_agent,
    _parse_claim_key,
    _strip_claim_key,
    _strip_ctrl_backslash,
)

class TestParseClaimKey:
    """Test _parse_claim_key parsing."""

    def test_ctrl_backslash(self) -> None:
        """ctrl+\\ → 0x1c raw + ESC[92;5u CSI."""
        raw, csi_u = _parse_claim_key("ctrl+\\")
        assert raw == b"\x1c"
        assert csi_u == b"\x1b[92;5u"

    def test_ctrl_right_bracket(self) -> None:
        """ctrl+] → 0x1d raw + ESC[93;5u CSI."""
        raw, csi_u = _parse_claim_key("ctrl+]")
        assert raw == b"\x1d"
        assert csi_u == b"\x1b[93;5u"

    def test_ctrl_a(self) -> None:
        """ctrl+a → 0x01 raw + ESC[97;5u CSI."""
        raw, csi_u = _parse_claim_key("ctrl+a")
        assert raw == b"\x01"
        assert csi_u == b"\x1b[97;5u"

    def test_case_insensitive(self) -> None:
        """Parsing is case-insensitive."""
        raw, csi_u = _parse_claim_key("Ctrl+A")
        assert raw == b"\x01"

    def test_invalid_format_no_ctrl(self) -> None:
        """Non ctrl+ format raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported claim_key format"):
            _parse_claim_key("alt+x")

    def test_invalid_format_empty(self) -> None:
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported claim_key format"):
            _parse_claim_key("")

    def test_invalid_multi_char(self) -> None:
        """Multiple characters after ctrl+ raises ValueError."""
        with pytest.raises(ValueError, match="single character"):
            _parse_claim_key("ctrl+ab")

    def test_matches_constants(self) -> None:
        """Default ctrl+\\ matches the module constants."""
        raw, csi_u = _parse_claim_key("ctrl+\\")
        assert raw == _CTRL_BACKSLASH
        assert csi_u == _CTRL_BACKSLASH_CSI_U

class TestStripClaimKey:
    """Test _strip_claim_key with parameterized bytes."""

    def test_strip_raw_byte(self) -> None:
        """Raw byte is stripped and detected."""
        raw, csi_u = _parse_claim_key("ctrl+\\")
        data, found = _strip_claim_key(b"hello\x1cworld", raw, csi_u)
        assert found is True
        assert data == b"helloworld"

    def test_strip_csi_u(self) -> None:
        """CSI u sequence is stripped and detected."""
        raw, csi_u = _parse_claim_key("ctrl+\\")
        data, found = _strip_claim_key(b"hello\x1b[92;5uworld", raw, csi_u)
        assert found is True
        assert data == b"helloworld"

    def test_strip_only_raw_yields_empty(self) -> None:
        raw, csi_u = _parse_claim_key("ctrl+]")
        data, found = _strip_claim_key(b"\x1d", raw, csi_u)
        assert found is True
        assert data == b""

    def test_strip_only_csi_u_yields_empty(self) -> None:
        raw, csi_u = _parse_claim_key("ctrl+]")
        data, found = _strip_claim_key(b"\x1b[93;5u", raw, csi_u)
        assert found is True
        assert data == b""

    def test_strip_both_variants(self) -> None:
        raw, csi_u = _parse_claim_key("ctrl+\\")
        data, found = _strip_claim_key(b"\x1c\x1b[92;5u", raw, csi_u)
        assert found is True
        assert data == b""

    def test_normal_data_unchanged(self) -> None:
        raw, csi_u = _parse_claim_key("ctrl+\\")
        data, found = _strip_claim_key(b"normal typing\r", raw, csi_u)
        assert found is False
        assert data == b"normal typing\r"

    def test_different_key_not_stripped(self) -> None:
        """Ctrl+] bytes are NOT stripped when looking for Ctrl+\\."""
        raw, csi_u = _parse_claim_key("ctrl+\\")
        original = b"\x1d"  # Ctrl+]
        data, found = _strip_claim_key(original, raw, csi_u)
        assert found is False
        assert data == original

    def test_custom_key_strips_correctly(self) -> None:
        """Custom key ctrl+] strips its own bytes."""
        raw, csi_u = _parse_claim_key("ctrl+]")
        data, found = _strip_claim_key(b"hello\x1dworld", raw, csi_u)
        assert found is True
        assert data == b"helloworld"

class TestStripCtrlBackslashCompat:
    """Test backward-compatible _strip_ctrl_backslash wrapper."""

    def test_strip_raw_byte(self) -> None:
        data, found = _strip_ctrl_backslash(b"hello\x1cworld")
        assert found is True
        assert data == b"helloworld"

    def test_strip_csi_u(self) -> None:
        data, found = _strip_ctrl_backslash(b"hello\x1b[92;5uworld")
        assert found is True
        assert data == b"helloworld"

    def test_normal_data_unchanged(self) -> None:
        data, found = _strip_ctrl_backslash(b"normal typing\r")
        assert found is False
        assert data == b"normal typing\r"

    def test_other_csi_u_not_stripped(self) -> None:
        """Other CSI u sequences (e.g. ESC[97;5u = Ctrl+a) are not stripped."""
        original = b"\x1b[97;5u"
        data, found = _strip_ctrl_backslash(original)
        assert found is False
        assert data == original

class TestClaimAgent:
    """Test _claim_agent fires correct command."""

    @patch("dictare.agent.mux.threading.Thread")
    def test_claim_starts_thread(self, mock_thread_cls: MagicMock) -> None:
        """_claim_agent spawns a daemon thread."""
        _claim_agent("claude", "http://127.0.0.1:8770")
        mock_thread_cls.assert_called_once()
        call_kwargs = mock_thread_cls.call_args
        assert call_kwargs.kwargs["daemon"] is True
        mock_thread_cls.return_value.start.assert_called_once()

    @patch("dictare.agent.mux.threading.Thread")
    def test_claim_thread_calls_control(self, mock_thread_cls: MagicMock) -> None:
        """The thread function calls client.control with correct command."""
        _claim_agent("cursor", "http://127.0.0.1:8770")
        # Extract the target function passed to Thread
        target_fn = mock_thread_cls.call_args.kwargs["target"]

        with patch("openvip.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            target_fn()
            mock_client_cls.assert_called_once_with("http://127.0.0.1:8770", timeout=3)
            mock_client.control.assert_called_once_with("output.set_agent:cursor")

    @patch("dictare.agent.mux.threading.Thread")
    def test_claim_swallows_exceptions(self, mock_thread_cls: MagicMock) -> None:
        """Engine errors don't crash the thread."""
        _claim_agent("aider", "http://127.0.0.1:9999")
        target_fn = mock_thread_cls.call_args.kwargs["target"]

        with patch("openvip.Client", side_effect=ConnectionRefusedError):
            # Should not raise
            target_fn()

class TestControllerRouting:
    """Test output.set_agent:<name> routing in controller."""

    def _make_controller(self) -> MagicMock:
        from dictare.app.controller import AppController

        ctrl = MagicMock(spec=AppController)
        ctrl._handle_app_command = AppController._handle_app_command.__get__(ctrl)
        return ctrl

    def test_set_agent_by_name(self) -> None:
        """output.set_agent:claude calls switch_to_agent('claude')."""
        ctrl = self._make_controller()
        result = ctrl._handle_app_command({"command": "output.set_agent:claude"})
        ctrl.switch_to_agent.assert_called_once_with("claude")
        assert result["status"] == "ok"

    def test_set_agent_cursor(self) -> None:
        """output.set_agent:cursor calls switch_to_agent('cursor')."""
        ctrl = self._make_controller()
        result = ctrl._handle_app_command({"command": "output.set_agent:cursor"})
        ctrl.switch_to_agent.assert_called_once_with("cursor")
        assert result["status"] == "ok"

class TestSwitchToAgentMode:
    """Test that switch_to_agent auto-enables agents mode."""

    def test_switch_enables_agent_mode(self) -> None:
        """switch_to_agent switches to agents mode if in keyboard mode."""
        from dictare.app.controller import AppController

        ctrl = MagicMock(spec=AppController)
        ctrl.switch_to_agent = AppController.switch_to_agent.__get__(ctrl)
        ctrl._engine = MagicMock()
        ctrl._engine.agent_mode = False

        ctrl.switch_to_agent("claude")

        ctrl._engine.set_output_mode.assert_called_once_with("agents")
        ctrl._engine.switch_to_agent_by_name.assert_called_once_with("claude")

    def test_switch_skips_mode_change_if_already_agents(self) -> None:
        """switch_to_agent does NOT call set_output_mode if already in agents mode."""
        from dictare.app.controller import AppController

        ctrl = MagicMock(spec=AppController)
        ctrl.switch_to_agent = AppController.switch_to_agent.__get__(ctrl)
        ctrl._engine = MagicMock()
        ctrl._engine.agent_mode = True

        ctrl.switch_to_agent("claude")

        ctrl._engine.set_output_mode.assert_not_called()
        ctrl._engine.switch_to_agent_by_name.assert_called_once_with("claude")
