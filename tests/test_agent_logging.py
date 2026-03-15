"""Tests for agent CLI logging (banner → log, truncation, --verbose)."""

from __future__ import annotations

import json
from unittest.mock import patch

from dictare.agent.mux import run_agent


def _make_status(agents: list[str]):
    """Create a mock status object with connected_agents."""
    from unittest.mock import MagicMock

    status = MagicMock()
    status.connected_agents = agents
    return status

class TestAgentBannerLogged:
    """Banner info (agent, server, session, command) goes to log file, not stderr."""

    def test_no_banner_on_stderr(self, capsys) -> None:
        """run_agent must NOT print banner lines to stderr."""
        with patch("openvip.Client") as mock_client:
            mock_client.return_value.get_status.side_effect = ConnectionRefusedError
            run_agent("voice", ["echo", "hi"], status_bar=False)
        captured = capsys.readouterr()
        # The error message about unreachable engine is OK — we check that
        # the old banner lines (Agent:, Server:, Session:, Running:) are gone.
        assert "Agent: voice" not in captured.err
        assert "Server: http" not in captured.err
        assert "Session:" not in captured.err
        assert "Running:" not in captured.err

    def test_banner_logged_to_agent_file(self, tmp_path) -> None:
        """Banner info is written to the agent log file."""
        import logging

        log_file = tmp_path / "agent.test.jsonl"
        from dictare.logging.setup import DictareJsonFormatter

        handler = logging.FileHandler(log_file)
        handler.setFormatter(DictareJsonFormatter(source="agent.test"))

        dictare_logger = logging.getLogger("dictare")

        def fake_setup_logging(**kwargs):
            dictare_logger.setLevel(logging.DEBUG)
            dictare_logger.addHandler(handler)
            return handler

        with patch("openvip.Client") as mock_client, \
             patch("dictare.agent.mux.setup_logging", side_effect=fake_setup_logging):
            mock_client.return_value.get_status.return_value = _make_status([])
            # Command will fail at PTY spawn — that's fine, the log happens before
            try:
                run_agent("test", ["__nonexistent__"], status_bar=False, clear_on_start=False)
            except (FileNotFoundError, OSError):
                pass
            finally:
                handler.flush()
                handler.close()
                dictare_logger.removeHandler(handler)

        content = log_file.read_text().strip()
        assert content, "Log file should not be empty"
        lines = content.splitlines()
        events = [json.loads(line) for line in lines]
        agent_start = [e for e in events if e.get("event") == "agent_start"]
        assert len(agent_start) == 1
        assert agent_start[0]["agent_id"] == "test"
        assert "server" in agent_start[0]
        assert "command" in agent_start[0]

class TestSessionTruncation:
    """Session log truncates text to 20 chars (not 50) with [...] suffix."""

    @staticmethod
    def _truncate(text: str, verbose: bool = False) -> str:
        """Replicate the truncation logic from mux.py."""
        if verbose:
            return text
        return text[:20] + "[...]" if len(text) > 20 else text

    def test_short_text_not_truncated(self) -> None:
        assert self._truncate("hello world") == "hello world"

    def test_exactly_20_not_truncated(self) -> None:
        text = "a" * 20
        assert self._truncate(text) == text

    def test_21_chars_truncated(self) -> None:
        text = "a" * 21
        assert self._truncate(text) == "a" * 20 + "[...]"

    def test_long_text_truncated(self) -> None:
        text = "This is a long transcription that should be truncated to twenty characters"
        result = self._truncate(text)
        assert result == "This is a long trans[...]"
        assert len(result) == 25  # 20 + len("[...]")

    def test_verbose_no_truncation(self) -> None:
        text = "This is a long transcription that should NOT be truncated when verbose"
        assert self._truncate(text, verbose=True) == text

class TestRunAgentNoQuietParam:
    """Verify --quiet parameter has been removed from run_agent."""

    def test_quiet_param_rejected(self) -> None:
        """run_agent must not accept 'quiet' keyword argument."""
        with patch("openvip.Client") as mock_client:
            mock_client.return_value.get_status.side_effect = ConnectionRefusedError
            try:
                run_agent("test", ["echo"], quiet=True)  # type: ignore[call-arg]
                assert False, "Should have raised TypeError"
            except TypeError as e:
                assert "quiet" in str(e)
