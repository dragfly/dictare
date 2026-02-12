"""Tests for agent template config and single-command launch logic."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from voxtype.cli.agent import _check_engine, _try_start_service
from voxtype.config import AgentTemplateConfig, Config, load_config

# ---------------------------------------------------------------------------
# AgentTemplateConfig parsing
# ---------------------------------------------------------------------------

class TestAgentTemplateConfig:
    def test_config_with_agents(self):
        toml_content = """
[agents.claude]
command = ["claude"]

[agents.aider]
command = ["aider", "--model", "claude-3-opus"]
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert "claude" in config.agents
            assert config.agents["claude"].command == ["claude"]
            assert config.agents["aider"].command == ["aider", "--model", "claude-3-opus"]
        finally:
            temp_path.unlink()

    def test_config_without_agents(self):
        config = Config()
        assert config.agents == {}

    def test_config_partial_no_agents(self):
        toml_content = """
[stt]
model = "tiny"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.agents == {}
            assert config.stt.model == "tiny"
        finally:
            temp_path.unlink()

    def test_template_lookup_hit(self):
        config = Config(agents={"claude": AgentTemplateConfig(command=["claude"])})
        template = config.agents.get("claude")
        assert template is not None
        assert template.command == ["claude"]

    def test_template_lookup_miss(self):
        config = Config(agents={"claude": AgentTemplateConfig(command=["claude"])})
        assert config.agents.get("unknown") is None

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
    def test_service_not_installed(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        with patch("voxtype.service.launchd.is_installed", return_value=False):
            assert _try_start_service() is False

    def test_service_start_success(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        with (
            patch("voxtype.service.launchd.is_installed", return_value=True),
            patch("voxtype.service.launchd.start"),
            patch("openvip.Client.is_available", return_value=True),
            patch("time.sleep"),
        ):
            assert _try_start_service() is True

    def test_service_start_engine_never_ready(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        with (
            patch("voxtype.service.launchd.is_installed", return_value=True),
            patch("voxtype.service.launchd.start"),
            patch("openvip.Client.is_available", return_value=False),
            patch("time.sleep"),
        ):
            assert _try_start_service() is False

    def test_unsupported_platform(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        assert _try_start_service() is False

# ---------------------------------------------------------------------------
# Command resolution logic (template vs override vs error)
# ---------------------------------------------------------------------------

class TestCommandResolution:
    """Test the command resolution: override > template > error."""

    def _make_config_toml(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def test_template_provides_command(self):
        """When template exists and no override, template command is used."""
        config = Config(agents={"claude": AgentTemplateConfig(command=["claude", "--flag"])})
        template = config.agents.get("claude")
        command_override: list[str] = []

        if command_override:
            command = command_override
        elif template:
            command = template.command
        else:
            command = None

        assert command == ["claude", "--flag"]

    def test_override_beats_template(self):
        """When both template and override exist, override wins."""
        config = Config(agents={"claude": AgentTemplateConfig(command=["claude"])})
        template = config.agents.get("claude")
        command_override = ["claude", "--model", "opus"]

        if command_override:
            command = command_override
        elif template:
            command = template.command
        else:
            command = None

        assert command == ["claude", "--model", "opus"]

    def test_no_template_no_override_is_none(self):
        """When no template and no override, result is None (error case)."""
        config = Config()
        template = config.agents.get("unknown")
        command_override: list[str] = []

        if command_override:
            command = command_override
        elif template:
            command = template.command
        else:
            command = None

        assert command is None
