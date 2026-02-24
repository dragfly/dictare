"""Tests for agent type config and single-command launch logic."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dictare.cli.agent import _check_engine, _try_start_service
from dictare.config import AgentTypesConfig, Config, load_config

_runner = CliRunner()

# ---------------------------------------------------------------------------
# AgentTypeConfig parsing
# ---------------------------------------------------------------------------


class TestAgentTypeConfig:
    def test_config_with_agent_types(self):
        toml_content = """
[agent_types]
default = "claude"

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
            assert config.agent_types.default == "claude"
            assert "claude" in config.agent_types
            assert config.agent_types.get("claude").command == ["claude"]
            assert config.agent_types.get("aider").command == ["aider", "--model", "claude-3-opus"]
        finally:
            temp_path.unlink()

    def test_config_without_agent_types(self):
        config = Config()
        assert not config.agent_types
        assert config.agent_types.default is None

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
            assert not config.agent_types
            assert config.stt.model == "tiny"
        finally:
            temp_path.unlink()

    def test_agent_type_lookup_hit(self):
        config = Config(agent_types=AgentTypesConfig(claude={"command": ["claude"]}))
        agent_type = config.agent_types.get("claude")
        assert agent_type is not None
        assert agent_type.command == ["claude"]

    def test_agent_type_lookup_miss(self):
        config = Config(agent_types=AgentTypesConfig(claude={"command": ["claude"]}))
        assert config.agent_types.get("unknown") is None

    def test_agent_type_with_description(self):
        config = Config(agent_types=AgentTypesConfig(**{
            "sonnet-4.6": {"command": ["claude", "--model", "claude-sonnet-4-6"], "description": "Claude Sonnet 4.6"}
        }))
        at = config.agent_types.get("sonnet-4.6")
        assert at.command == ["claude", "--model", "claude-sonnet-4-6"]
        assert at.description == "Claude Sonnet 4.6"

    def test_default_agent_type(self):
        config = Config(
            agent_types=AgentTypesConfig(default="claude", claude={"command": ["claude"]}),
        )
        assert config.agent_types.default == "claude"
        default_at = config.agent_types.get(config.agent_types.default)
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
            patch("dictare.daemon.launchd.is_installed", return_value=False),
            patch("dictare.daemon.launchd.start", mock_start),
        ):
            _try_start_service()  # fire-and-forget, no return value
            mock_start.assert_not_called()

    def test_service_installed_calls_start(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        mock_start = MagicMock()
        with (
            patch("dictare.daemon.launchd.is_installed", return_value=True),
            patch("dictare.daemon.launchd.start", mock_start),
        ):
            _try_start_service()
            mock_start.assert_called_once()

    def test_unsupported_platform_noop(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        _try_start_service()  # should not raise


# ---------------------------------------------------------------------------
# Command resolution logic (template vs override vs error)
# ---------------------------------------------------------------------------


def _resolve_command(
    config: Config,
    command_override: list[str],
    agent_type_name: str | None = None,
) -> list[str] | None:
    """Replicate the CLI command resolution logic for testing."""
    if command_override:
        return command_override
    type_key = agent_type_name or config.agent_types.default
    if type_key is None:
        return None
    agent_type = config.agent_types.get(type_key)
    return agent_type.command if agent_type else None


class TestCommandResolution:
    """Test the command resolution: override > --type > agent_types.default > error."""

    def test_explicit_type_provides_command(self):
        """--type picks command from agent_types regardless of session name."""
        config = Config(agent_types=AgentTypesConfig(**{"claude-sonnet": {"command": ["claude", "--model", "sonnet"]}}))
        command = _resolve_command(config, [], agent_type_name="claude-sonnet")
        assert command == ["claude", "--model", "sonnet"]

    def test_default_agent_type_used_when_no_type_flag(self):
        """Without --type, agent_types.default is the fallback."""
        config = Config(
            agent_types=AgentTypesConfig(default="claude-sonnet", **{"claude-sonnet": {"command": ["claude", "--model", "sonnet"]}}),
        )
        command = _resolve_command(config, [], agent_type_name=None)
        assert command == ["claude", "--model", "sonnet"]

    def test_override_beats_type(self):
        """Explicit command override wins over --type."""
        config = Config(agent_types=AgentTypesConfig(claude={"command": ["claude"]}))
        command = _resolve_command(config, ["claude", "--model", "opus"], agent_type_name="claude")
        assert command == ["claude", "--model", "opus"]

    def test_no_type_no_default_returns_none(self):
        """No --type and no agent_types.default → error (None)."""
        config = Config(agent_types=AgentTypesConfig(claude={"command": ["claude"]}))
        command = _resolve_command(config, [], agent_type_name=None)
        assert command is None

    def test_type_not_in_config_returns_none(self):
        """--type pointing to unknown key → error (None)."""
        config = Config(agent_types=AgentTypesConfig(claude={"command": ["claude"]}))
        command = _resolve_command(config, [], agent_type_name="nonexistent")
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
            patch("dictare.daemon.launchd.is_installed", side_effect=RuntimeError("boom")),
        ):
            _try_start_service()  # must not raise

    def test_try_start_service_returns_none(self, monkeypatch):
        """_try_start_service must not return a truthy/falsy gate value."""
        monkeypatch.setattr("sys.platform", "darwin")
        with (
            patch("dictare.daemon.launchd.is_installed", return_value=False),
            patch("dictare.daemon.launchd.start"),
        ):
            result = _try_start_service()
            assert result is None, (
                "_try_start_service must return None (fire-and-forget), "
                "not a bool that gates agent startup"
            )


# ---------------------------------------------------------------------------
# CLI contract: agent_id required, --type selects command template
# ---------------------------------------------------------------------------


def _make_config(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def _invoke_agent(args: list[str], config_path: Path):
    """Invoke the agent CLI command with a fake config, engine unreachable."""
    from dictare.cli import app

    with (
        patch("dictare.cli.agent._check_engine", return_value=False),
        patch("dictare.cli.agent._try_start_service"),
        patch("dictare.agent.run_agent", return_value=0),
        patch("dictare.config.get_config_path", return_value=config_path),
    ):
        return _runner.invoke(app, ["agent"] + args, catch_exceptions=False)


class TestAgentCLIContract:
    """Verify the CLI contract: name required, --type selects template."""

    def setup_method(self):
        self.config = _make_config("""
[agent_types]
default = "claude-sonnet"

[agent_types.claude-sonnet]
command = ["claude", "--model", "claude-sonnet-4-6"]
description = "Claude Sonnet"

[agent_types.claude-opus]
command = ["claude", "--model", "claude-opus-4-6"]
description = "Claude Opus"
""")

    def teardown_method(self):
        self.config.unlink(missing_ok=True)

    def test_missing_agent_id_exits_nonzero(self):
        """AGENT_ID is required — omitting it must fail."""
        result = _invoke_agent([], self.config)
        assert result.exit_code != 0

    def test_agent_id_with_type_uses_type_command(self):
        """dictare agent Pippo --type claude-opus → uses claude-opus command."""
        launched: list[list[str]] = []

        def fake_run_agent(agent_id, command, **_kw):
            launched.append((agent_id, command))
            return 0

        with (
            patch("dictare.cli.agent._check_engine", return_value=True),
            patch("dictare.agent.run_agent", side_effect=fake_run_agent),
            patch("dictare.config.get_config_path", return_value=self.config),
        ):
            from dictare.cli import app
            result = _runner.invoke(app, ["agent", "Pippo", "--type", "claude-opus"], catch_exceptions=False)

        assert result.exit_code == 0
        assert launched[0] == ("Pippo", ["claude", "--model", "claude-opus-4-6"])

    def test_agent_id_without_type_uses_default(self):
        """dictare agent Pippo (no --type) → uses agent_types.default command."""
        launched: list[list[str]] = []

        def fake_run_agent(agent_id, command, **_kw):
            launched.append((agent_id, command))
            return 0

        with (
            patch("dictare.cli.agent._check_engine", return_value=True),
            patch("dictare.agent.run_agent", side_effect=fake_run_agent),
            patch("dictare.config.get_config_path", return_value=self.config),
        ):
            from dictare.cli import app
            result = _runner.invoke(app, ["agent", "Pippo"], catch_exceptions=False)

        assert result.exit_code == 0
        assert launched[0] == ("Pippo", ["claude", "--model", "claude-sonnet-4-6"])

    def test_agent_id_unknown_type_exits_nonzero(self):
        """--type pointing to non-existent key → exit 1."""
        result = _invoke_agent(["Pippo", "--type", "nonexistent"], self.config)
        assert result.exit_code != 0

    def test_no_default_no_type_exits_nonzero(self):
        """No --type and no agent_types.default → exit 1."""
        config = _make_config("""
[agent_types.claude-sonnet]
command = ["claude"]
""")
        try:
            result = _invoke_agent(["Pippo"], config)
            assert result.exit_code != 0
        finally:
            config.unlink(missing_ok=True)

    def test_command_override_ignores_type(self):
        """-- command override wins over --type."""
        launched: list[list[str]] = []

        def fake_run_agent(agent_id, command, **_kw):
            launched.append((agent_id, command))
            return 0

        with (
            patch("dictare.cli.agent._check_engine", return_value=True),
            patch("dictare.agent.run_agent", side_effect=fake_run_agent),
            patch("dictare.config.get_config_path", return_value=self.config),
        ):
            from dictare.cli import app
            result = _runner.invoke(
                app, ["agent", "Pippo", "--", "my-tool", "--flag"], catch_exceptions=False
            )

        assert result.exit_code == 0
        assert launched[0] == ("Pippo", ["my-tool", "--flag"])

    def test_session_name_is_independent_of_type(self):
        """Session id in run_agent must be the name, not the type key."""
        launched: list[tuple] = []

        def fake_run_agent(agent_id, command, **_kw):
            launched.append((agent_id, command))
            return 0

        with (
            patch("dictare.cli.agent._check_engine", return_value=True),
            patch("dictare.agent.run_agent", side_effect=fake_run_agent),
            patch("dictare.config.get_config_path", return_value=self.config),
        ):
            from dictare.cli import app
            _runner.invoke(app, ["agent", "frontend", "--type", "claude-opus"], catch_exceptions=False)

        agent_id, command = launched[0]
        assert agent_id == "frontend"          # session name = what the user said
        assert "claude-opus-4-6" in command    # command from the type
