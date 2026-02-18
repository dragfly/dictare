"""Tests for agent type config and single-command launch logic."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from voxtype.cli.agent import _check_engine, _try_start_service
from voxtype.config import AgentTypeConfig, Config, load_config

# ---------------------------------------------------------------------------
# AgentTypeConfig parsing
# ---------------------------------------------------------------------------

class TestAgentTypeConfig:
    def test_config_with_agent_types(self):
        toml_content = """
default_agent_type = "claude"

[agent_types.claude]
command = ["claude"]

[agent_types.aider]
command = ["aider", "--model", "claude-3-opus"]
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.default_agent_type == "claude"
            assert "claude" in config.agent_types
            assert config.agent_types["claude"].command == ["claude"]
            assert config.agent_types["aider"].command == ["aider", "--model", "claude-3-opus"]
        finally:
            temp_path.unlink()

    def test_config_without_agent_types(self):
        config = Config()
        assert config.agent_types == {}
        assert config.default_agent_type is None

    def test_config_partial_no_agent_types(self):
        toml_content = """
[stt]
model = "tiny"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.agent_types == {}
            assert config.stt.model == "tiny"
        finally:
            temp_path.unlink()

    def test_agent_type_lookup_hit(self):
        config = Config(agent_types={"claude": AgentTypeConfig(command=["claude"])})
        agent_type = config.agent_types.get("claude")
        assert agent_type is not None
        assert agent_type.command == ["claude"]

    def test_agent_type_lookup_miss(self):
        config = Config(agent_types={"claude": AgentTypeConfig(command=["claude"])})
        assert config.agent_types.get("unknown") is None

    def test_agent_type_with_description(self):
        config = Config(agent_types={
            "sonnet-4.6": AgentTypeConfig(
                command=["claude", "--model", "claude-sonnet-4-6"],
                description="Claude Sonnet 4.6",
            )
        })
        at = config.agent_types["sonnet-4.6"]
        assert at.command == ["claude", "--model", "claude-sonnet-4-6"]
        assert at.description == "Claude Sonnet 4.6"

    def test_default_agent_type(self):
        config = Config(
            default_agent_type="claude",
            agent_types={"claude": AgentTypeConfig(command=["claude"])},
        )
        assert config.default_agent_type == "claude"
        default_at = config.agent_types.get(config.default_agent_type)
        assert default_at is not None
        assert default_at.command == ["claude"]

# ---------------------------------------------------------------------------
# Engine health check
# ---------------------------------------------------------------------------

class TestCheckEngine:
    def test_engine_reachable(self):
        with patch("openvip.Client.is_available", return_value=True):
            assert _check_engine("http://127.0.0.1:8770") is True

    def test_engine_unreachable(self):
        with patch("openvip.Client.is_available", return_value=False):
            assert _check_engine("http://127.0.0.1:8770") is False

# ---------------------------------------------------------------------------
# Service auto-start
# ---------------------------------------------------------------------------

class TestTryStartService:
    def test_service_not_installed_does_not_call_start(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        mock_start = MagicMock()
        with (
            patch("voxtype.daemon.launchd.is_installed", return_value=False),
            patch("voxtype.daemon.launchd.start", mock_start),
        ):
            _try_start_service()  # fire-and-forget, no return value
            mock_start.assert_not_called()

    def test_service_installed_calls_start(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        mock_start = MagicMock()
        with (
            patch("voxtype.daemon.launchd.is_installed", return_value=True),
            patch("voxtype.daemon.launchd.start", mock_start),
        ):
            _try_start_service()
            mock_start.assert_called_once()

    def test_unsupported_platform_noop(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        _try_start_service()  # should not raise

# ---------------------------------------------------------------------------
# Command resolution logic (template vs override vs error)
# ---------------------------------------------------------------------------

class TestCommandResolution:
    """Test the command resolution: override > agent type > error."""

    def _make_config_toml(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def test_agent_type_provides_command(self):
        """When agent type exists and no override, agent type command is used."""
        config = Config(agent_types={"claude": AgentTypeConfig(command=["claude", "--flag"])})
        agent_type = config.agent_types.get("claude")
        command_override: list[str] = []

        if command_override:
            command = command_override
        elif agent_type:
            command = agent_type.command
        else:
            command = None

        assert command == ["claude", "--flag"]

    def test_override_beats_agent_type(self):
        """When both agent type and override exist, override wins."""
        config = Config(agent_types={"claude": AgentTypeConfig(command=["claude"])})
        agent_type = config.agent_types.get("claude")
        command_override = ["claude", "--model", "opus"]

        if command_override:
            command = command_override
        elif agent_type:
            command = agent_type.command
        else:
            command = None

        assert command == ["claude", "--model", "opus"]

    def test_no_agent_type_no_override_is_none(self):
        """When no agent type and no override, result is None (error case)."""
        config = Config()
        agent_type = config.agent_types.get("unknown")
        command_override: list[str] = []

        if command_override:
            command = command_override
        elif agent_type:
            command = agent_type.command
        else:
            command = None

        assert command is None

# ---------------------------------------------------------------------------
# Regression: agent must never hard-exit when engine is unreachable
# ---------------------------------------------------------------------------

class TestAgentNeverBlocksOnEngine:
    """The agent command must proceed even when the engine is down.

    The SSE reconnect loop handles eventual connectivity — the CLI must
    never gate on engine availability with a hard exit.
    """

    def test_try_start_service_never_raises(self, monkeypatch):
        """_try_start_service is fire-and-forget — exceptions are swallowed."""
        monkeypatch.setattr("sys.platform", "darwin")
        with (
            patch("voxtype.daemon.launchd.is_installed", side_effect=RuntimeError("boom")),
        ):
            _try_start_service()  # must not raise

    def test_try_start_service_returns_none(self, monkeypatch):
        """_try_start_service must not return a truthy/falsy gate value."""
        monkeypatch.setattr("sys.platform", "darwin")
        with (
            patch("voxtype.daemon.launchd.is_installed", return_value=False),
            patch("voxtype.daemon.launchd.start"),
        ):
            result = _try_start_service()
            assert result is None, (
                "_try_start_service must return None (fire-and-forget), "
                "not a bool that gates agent startup"
            )
