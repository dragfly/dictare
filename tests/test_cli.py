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
                patch("voxtype.cli.config.get_config_path", return_value=config_path),
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
                patch("voxtype.cli.config.get_config_path", return_value=config_path),
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
                patch("voxtype.cli.config.get_config_path", return_value=config_path),
                patch("voxtype.config.get_config_dir", return_value=config_dir),
                patch("subprocess.run"),
                patch.dict("os.environ", {"VISUAL": "vim", "EDITOR": ""}),
            ):
                result = runner.invoke(app, ["config", "edit"])

            assert config_path.exists()
            assert result.exit_code == 0
