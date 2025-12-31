"""Tests for CLI interface."""

from typer.testing import CliRunner

from voxtype import __version__
from voxtype.cli import app

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
        assert "voxtype" in result.stdout.lower()

    def test_run_help(self) -> None:
        """Test 'run --help' shows run command help."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--model" in result.stdout
        assert "--language" in result.stdout
        assert "--vad" in result.stdout

    def test_config_help(self) -> None:
        """Test 'config --help' shows config command help."""
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0

    def test_check_help(self) -> None:
        """Test 'check --help' shows check command help."""
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0

class TestCLIConfigCommands:
    """Test config-related CLI commands."""

    def test_config_path(self) -> None:
        """Test 'config path' shows config path."""
        result = runner.invoke(app, ["config", "path"])
        assert result.exit_code == 0
        assert "voxtype" in result.stdout.lower()

    def test_config_list(self) -> None:
        """Test 'config list' shows available config keys."""
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "stt.model_size" in result.stdout
