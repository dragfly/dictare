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
            patch("dictare.cli.agent.shutil.which", return_value="/usr/bin/claude"),
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


class TestAgentLiveDangerously:
    """Tests for --live-dangerously flag and config defaults on 'dictare agent'."""

    def _make_config(
        self,
        live_dangerously_args: list[str] | None = None,
        global_live_dangerously: bool = False,
        profile_live_dangerously: bool | None = None,
    ) -> object:
        from dictare.config import AgentProfileConfig, AgentProfilesConfig, ClientConfig, Config

        profile_kwargs: dict = {
            "command": ["claude", "--model", "claude-sonnet-4-6"],
            "live_dangerously_args": live_dangerously_args or [],
        }
        if profile_live_dangerously is not None:
            profile_kwargs["live_dangerously"] = profile_live_dangerously

        at = AgentProfileConfig(**profile_kwargs)
        cfg = Config()
        cfg = cfg.model_copy(update={
            "agent_profiles": AgentProfilesConfig(
                default="sonnet", live_dangerously=global_live_dangerously, sonnet=at,
            ),
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
            patch("dictare.cli.agent.shutil.which", return_value="/usr/bin/claude"),
        ):
            result = runner.invoke(app, ["agent"] + args)

        return result, captured

    # --- CLI flag ---

    def test_cli_flag_inserts_live_dangerously_args(self) -> None:
        """--live-dangerously inserts live_dangerously_args after argv[0]."""
        cfg = self._make_config(live_dangerously_args=["--dangerously-skip-permissions"])
        result, captured = self._invoke_agent(
            ["myproject", "--type", "sonnet", "--live-dangerously"], cfg,
        )
        assert result.exit_code == 0
        assert captured == [["claude", "--dangerously-skip-permissions", "--model", "claude-sonnet-4-6"]]

    def test_cli_flag_without_args_warns(self) -> None:
        """--live-dangerously with no live_dangerously_args shows a warning."""
        cfg = self._make_config(live_dangerously_args=[])
        result, captured = self._invoke_agent(
            ["myproject", "--type", "sonnet", "--live-dangerously"], cfg,
        )
        assert result.exit_code == 0
        assert "Warning" in result.output
        assert captured == [["claude", "--model", "claude-sonnet-4-6"]]

    def test_cli_flag_with_command_override_ignored(self) -> None:
        """--live-dangerously is silently ignored with explicit command override."""
        cfg = self._make_config(live_dangerously_args=["--dangerously-skip-permissions"])
        result, captured = self._invoke_agent(
            ["myproject", "--live-dangerously", "--", "aider", "--model", "gpt-4"], cfg,
        )
        assert result.exit_code == 0
        assert captured == [["aider", "--model", "gpt-4"]]

    # --- Global default ---

    def test_global_default_applies(self) -> None:
        """agent_profiles.live_dangerously = true activates without CLI flag."""
        cfg = self._make_config(
            live_dangerously_args=["--dangerously-skip-permissions"],
            global_live_dangerously=True,
        )
        result, captured = self._invoke_agent(["myproject", "--type", "sonnet"], cfg)
        assert result.exit_code == 0
        assert captured == [["claude", "--dangerously-skip-permissions", "--model", "claude-sonnet-4-6"]]

    def test_global_default_false_does_not_apply(self) -> None:
        """agent_profiles.live_dangerously = false (default) does nothing."""
        cfg = self._make_config(
            live_dangerously_args=["--dangerously-skip-permissions"],
            global_live_dangerously=False,
        )
        result, captured = self._invoke_agent(["myproject", "--type", "sonnet"], cfg)
        assert result.exit_code == 0
        assert captured == [["claude", "--model", "claude-sonnet-4-6"]]

    # --- Per-profile override ---

    def test_profile_override_true_over_global_false(self) -> None:
        """Profile live_dangerously=true overrides global false."""
        cfg = self._make_config(
            live_dangerously_args=["--dangerously-skip-permissions"],
            global_live_dangerously=False,
            profile_live_dangerously=True,
        )
        result, captured = self._invoke_agent(["myproject", "--type", "sonnet"], cfg)
        assert result.exit_code == 0
        assert captured == [["claude", "--dangerously-skip-permissions", "--model", "claude-sonnet-4-6"]]

    def test_profile_override_false_over_global_true(self) -> None:
        """Profile live_dangerously=false overrides global true."""
        cfg = self._make_config(
            live_dangerously_args=["--dangerously-skip-permissions"],
            global_live_dangerously=True,
            profile_live_dangerously=False,
        )
        result, captured = self._invoke_agent(["myproject", "--type", "sonnet"], cfg)
        assert result.exit_code == 0
        assert captured == [["claude", "--model", "claude-sonnet-4-6"]]

    def test_profile_none_falls_through_to_global(self) -> None:
        """Profile live_dangerously=None (unset) falls through to global."""
        cfg = self._make_config(
            live_dangerously_args=["--dangerously-skip-permissions"],
            global_live_dangerously=True,
            profile_live_dangerously=None,
        )
        result, captured = self._invoke_agent(["myproject", "--type", "sonnet"], cfg)
        assert result.exit_code == 0
        assert captured == [["claude", "--dangerously-skip-permissions", "--model", "claude-sonnet-4-6"]]

    # --- CLI flag always wins ---

    def test_cli_flag_wins_over_profile_false(self) -> None:
        """CLI --live-dangerously wins even when profile says false."""
        cfg = self._make_config(
            live_dangerously_args=["--dangerously-skip-permissions"],
            profile_live_dangerously=False,
        )
        result, captured = self._invoke_agent(
            ["myproject", "--type", "sonnet", "--live-dangerously"], cfg,
        )
        assert result.exit_code == 0
        assert captured == [["claude", "--dangerously-skip-permissions", "--model", "claude-sonnet-4-6"]]

    # --- Config model ---

    def test_agent_profile_config_live_dangerously_defaults_none(self) -> None:
        """AgentProfileConfig.live_dangerously defaults to None."""
        from dictare.config import AgentProfileConfig

        at = AgentProfileConfig.model_validate({"command": ["claude"]})
        assert at.live_dangerously is None

    def test_agent_profiles_config_live_dangerously_defaults_false(self) -> None:
        """AgentProfilesConfig.live_dangerously defaults to False."""
        from dictare.config import AgentProfilesConfig

        cfg = AgentProfilesConfig()
        assert cfg.live_dangerously is False

    def test_toml_with_global_live_dangerously(self) -> None:
        """Global live_dangerously parses correctly from TOML."""
        import tempfile
        from pathlib import Path

        from dictare.config import load_config

        toml = """
[agent_profiles]
default = "claude"
live_dangerously = true

[agent_profiles.claude]
command = ["claude"]
live_dangerously_args = ["--dangerously-skip-permissions"]
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.agent_profiles.live_dangerously is True
            profile = config.agent_profiles.get("claude")
            assert profile.live_dangerously is None  # not set at profile level
        finally:
            temp_path.unlink()

    def test_toml_with_profile_live_dangerously(self) -> None:
        """Per-profile live_dangerously parses correctly from TOML."""
        import tempfile
        from pathlib import Path

        from dictare.config import load_config

        toml = """
[agent_profiles]
default = "claude"

[agent_profiles.claude]
command = ["claude"]
live_dangerously_args = ["--dangerously-skip-permissions"]
live_dangerously = true
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.agent_profiles.live_dangerously is False  # global default
            profile = config.agent_profiles.get("claude")
            assert profile.live_dangerously is True
        finally:
            temp_path.unlink()
