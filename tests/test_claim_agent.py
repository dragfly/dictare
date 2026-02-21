"""Tests for Ctrl+\\ agent claim in PTY stdin reader."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from voxtype.agent.mux import _CTRL_BACKSLASH, _claim_agent


class TestCtrlBackslashIntercept:
    """Unit tests for Ctrl+\\ interception logic."""

    def test_ctrl_backslash_byte_value(self) -> None:
        """Ctrl+\\ is 0x1c in raw terminal mode."""
        assert _CTRL_BACKSLASH == b"\x1c"

    def test_ctrl_backslash_stripped_from_data(self) -> None:
        """Ctrl+\\ is removed from data before forwarding."""
        data = b"hello\x1cworld"
        cleaned = data.replace(_CTRL_BACKSLASH, b"")
        assert cleaned == b"helloworld"

    def test_only_ctrl_backslash_yields_empty(self) -> None:
        """Data containing only Ctrl+\\ becomes empty."""
        data = b"\x1c"
        cleaned = data.replace(_CTRL_BACKSLASH, b"")
        assert cleaned == b""

    def test_normal_data_unchanged(self) -> None:
        """Data without Ctrl+\\ passes through unchanged."""
        data = b"normal typing\r"
        assert _CTRL_BACKSLASH not in data


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
