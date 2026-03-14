"""Tests for CLI interface."""

from typer.testing import CliRunner

from dictare import __version__
from dictare.cli import app

runner = CliRunner()

class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_version_flag(self) -> None:
        """Test --version flag shows version."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_help_flag(self) -> None:
        """Test --help flag shows help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "dictare" in result.stdout.lower()

    def test_config_help(self) -> None:
        """Test 'config --help' shows config command help."""
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0

    def test_dependencies_help(self) -> None:
        """Test 'dependencies --help' shows command help."""
        result = runner.invoke(app, ["dependencies", "--help"])
        assert result.exit_code == 0

class TestCLIConfigCommands:
    """Test config-related CLI commands."""

    def test_config_list(self) -> None:
        """Test 'config list' shows available config keys."""
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "stt.model" in result.stdout

    def test_config_edit_uses_editor_from_config(self) -> None:
        """'config edit' uses editor from config, falls back to $EDITOR."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text('editor = "myeditor --flag"\n')

            with (
                patch("dictare.cli.config.get_config_path", return_value=config_path),
                patch("subprocess.run") as mock_run,
            ):
                result = runner.invoke(app, ["config", "edit"])

            mock_run.assert_called_once_with(
                ["myeditor", "--flag", str(config_path)], check=True,
            )
            assert result.exit_code == 0

    def test_config_edit_falls_back_to_env_editor(self) -> None:
        """'config edit' uses $EDITOR when config editor is empty."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text("")  # No editor field

            with (
                patch("dictare.cli.config.get_config_path", return_value=config_path),
                patch("subprocess.run") as mock_run,
                patch.dict("os.environ", {"VISUAL": "", "EDITOR": "nano"}),
            ):
                result = runner.invoke(app, ["config", "edit"])

            mock_run.assert_called_once_with(
                ["nano", str(config_path)], check=True,
            )
            assert result.exit_code == 0

    def test_config_edit_creates_config_if_missing(self) -> None:
        """'config edit' creates default config when file doesn't exist."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_path = config_dir / "config.toml"

            with (
                patch("dictare.cli.config.get_config_path", return_value=config_path),
                patch("dictare.config.get_config_dir", return_value=config_dir),
                patch("subprocess.run"),
                patch.dict("os.environ", {"VISUAL": "vim", "EDITOR": ""}),
            ):
                result = runner.invoke(app, ["config", "edit"])

            assert config_path.exists()
            assert result.exit_code == 0

class TestAgentContinue:
    """Tests for --continue / -C flag on 'dictare agent'."""

    def _make_config(self, continue_args: list[str] | None = None) -> object:
        from dictare.config import AgentProfileConfig, AgentProfilesConfig, ClientConfig, Config

        at = AgentProfileConfig(
            command=["claude", "--model", "claude-sonnet-4-6"],
            continue_args=continue_args or [],
        )
        cfg = Config()
        cfg = cfg.model_copy(update={
            "agent_profiles": AgentProfilesConfig(default="sonnet", sonnet=at),
            "client": ClientConfig(url="http://127.0.0.1:8770", status_bar=False),
        })
        return cfg

    def _invoke_agent(self, args: list[str], cfg: object) -> tuple[object, list]:
        from unittest.mock import patch

        captured: list[list[str]] = []

        def fake_run_agent(agent_id: str, command: list[str], **kwargs: object) -> int:
            captured.append(command)
            return 0

        with (
            patch("dictare.cli.agent._check_engine", return_value=True),
            patch("dictare.config.load_config", return_value=cfg),
            patch("dictare.agent.run_agent", side_effect=fake_run_agent),
        ):
            result = runner.invoke(app, ["agent"] + args)

        return result, captured

    def test_continue_inserts_continue_args_after_argv0(self) -> None:
        """--continue prepends continue_args after argv[0]."""
        cfg = self._make_config(continue_args=["-c"])
        result, captured = self._invoke_agent(["myproject", "--type", "sonnet", "--continue"], cfg)
        assert result.exit_code == 0
        assert captured == [["claude", "-c", "--model", "claude-sonnet-4-6"]]

    def test_short_flag_c_works(self) -> None:
        """-C is an alias for --continue."""
        cfg = self._make_config(continue_args=["-c"])
        result, captured = self._invoke_agent(["myproject", "--type", "sonnet", "-C"], cfg)
        assert result.exit_code == 0
        assert captured == [["claude", "-c", "--model", "claude-sonnet-4-6"]]

    def test_continue_without_continue_args_warns(self) -> None:
        """--continue with no continue_args configured shows a warning."""
        cfg = self._make_config(continue_args=[])
        result, captured = self._invoke_agent(["myproject", "--type", "sonnet", "--continue"], cfg)
        assert result.exit_code == 0
        assert "Warning" in result.output
        # Command runs unchanged
        assert captured == [["claude", "--model", "claude-sonnet-4-6"]]

    def test_continue_with_command_override_ignored(self) -> None:
        """--continue is silently ignored when explicit command is given via --."""
        cfg = self._make_config(continue_args=["-c"])
        result, captured = self._invoke_agent(
            ["myproject", "--continue", "--", "aider", "--model", "gpt-4"], cfg
        )
        assert result.exit_code == 0
        # Command override wins; -c not inserted
        assert captured == [["aider", "--model", "gpt-4"]]

    def test_agent_profile_config_parses_continue_args(self) -> None:
        """AgentProfileConfig correctly parses continue_args from TOML data."""
        from dictare.config import AgentProfileConfig

        at = AgentProfileConfig.model_validate({
            "command": ["claude"],
            "continue_args": ["-c"],
        })
        assert at.continue_args == ["-c"]

    def test_agent_profile_config_continue_args_defaults_empty(self) -> None:
        """continue_args defaults to [] when not specified."""
        from dictare.config import AgentProfileConfig

        at = AgentProfileConfig.model_validate({"command": ["claude"]})
        assert at.continue_args == []
