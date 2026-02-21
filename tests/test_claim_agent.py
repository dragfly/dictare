"""Tests for Ctrl+\\ agent claim in PTY stdin reader."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from voxtype.agent.mux import (
    _CTRL_BACKSLASH,
    _CTRL_BACKSLASH_CSI_U,
    _claim_agent,
    _strip_ctrl_backslash,
)


class TestCtrlBackslashIntercept:
    """Unit tests for Ctrl+\\ interception logic."""

    def test_ctrl_backslash_byte_value(self) -> None:
        """Ctrl+\\ is 0x1c in raw terminal mode."""
        assert _CTRL_BACKSLASH == b"\x1c"

    def test_csi_u_byte_value(self) -> None:
        """Kitty keyboard protocol encodes Ctrl+\\ as ESC[92;5u."""
        assert _CTRL_BACKSLASH_CSI_U == b"\x1b[92;5u"

    def test_strip_raw_byte(self) -> None:
        """Standard 0x1c byte is stripped and detected."""
        data, found = _strip_ctrl_backslash(b"hello\x1cworld")
        assert found is True
        assert data == b"helloworld"

    def test_strip_csi_u(self) -> None:
        """Kitty CSI u sequence is stripped and detected."""
        data, found = _strip_ctrl_backslash(b"hello\x1b[92;5uworld")
        assert found is True
        assert data == b"helloworld"

    def test_strip_only_raw_byte_yields_empty(self) -> None:
        """Data containing only 0x1c becomes empty."""
        data, found = _strip_ctrl_backslash(b"\x1c")
        assert found is True
        assert data == b""

    def test_strip_only_csi_u_yields_empty(self) -> None:
        """Data containing only CSI u sequence becomes empty."""
        data, found = _strip_ctrl_backslash(b"\x1b[92;5u")
        assert found is True
        assert data == b""

    def test_strip_both_variants(self) -> None:
        """Both raw byte and CSI u in same data are stripped."""
        data, found = _strip_ctrl_backslash(b"\x1c\x1b[92;5u")
        assert found is True
        assert data == b""

    def test_normal_data_unchanged(self) -> None:
        """Data without Ctrl+\\ passes through unchanged."""
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

    @patch("voxtype.agent.mux.threading.Thread")
    def test_claim_starts_thread(self, mock_thread_cls: MagicMock) -> None:
        """_claim_agent spawns a daemon thread."""
        _claim_agent("claude", "http://127.0.0.1:8770")
        mock_thread_cls.assert_called_once()
        call_kwargs = mock_thread_cls.call_args
        assert call_kwargs.kwargs["daemon"] is True
        mock_thread_cls.return_value.start.assert_called_once()

    @patch("voxtype.agent.mux.threading.Thread")
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

    @patch("voxtype.agent.mux.threading.Thread")
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
        from voxtype.app.controller import AppController

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
        from voxtype.app.controller import AppController

        ctrl = MagicMock(spec=AppController)
        ctrl.switch_to_agent = AppController.switch_to_agent.__get__(ctrl)
        ctrl._engine = MagicMock()
        ctrl._engine.agent_mode = False

        ctrl.switch_to_agent("claude")

        ctrl._engine.set_output_mode.assert_called_once_with("agents")
        ctrl._engine.switch_to_agent_by_name.assert_called_once_with("claude")

    def test_switch_skips_mode_change_if_already_agents(self) -> None:
        """switch_to_agent does NOT call set_output_mode if already in agents mode."""
        from voxtype.app.controller import AppController

        ctrl = MagicMock(spec=AppController)
        ctrl.switch_to_agent = AppController.switch_to_agent.__get__(ctrl)
        ctrl._engine = MagicMock()
        ctrl._engine.agent_mode = True

        ctrl.switch_to_agent("claude")

        ctrl._engine.set_output_mode.assert_not_called()
        ctrl._engine.switch_to_agent_by_name.assert_called_once_with("claude")
