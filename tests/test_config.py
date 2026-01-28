"""Tests for configuration module."""

import tempfile
from pathlib import Path

from voxtype.config import (
    AudioConfig,
    CommandConfig,
    Config,
    HotkeyConfig,
    OutputConfig,
    STTConfig,
    load_config,
)


class TestConfigDefaults:
    """Test default configuration values."""

    def test_audio_config_defaults(self) -> None:
        """Test AudioConfig has correct defaults."""
        config = AudioConfig()
        assert config.sample_rate == 16000
        assert config.channels == 1
        assert config.device is None
        assert config.audio_feedback is True

    def test_stt_config_defaults(self) -> None:
        """Test STTConfig has correct defaults."""
        config = STTConfig()
        assert config.model == "large-v3-turbo"
        assert config.language == "auto"
        assert config.device == "auto"
        assert config.compute_type == "int8"
        assert config.beam_size == 5

    def test_hotkey_config_defaults(self) -> None:
        """Test HotkeyConfig has correct defaults."""
        import sys
        config = HotkeyConfig()
        # Platform-specific: Command on macOS, Scroll Lock on Linux
        expected_key = "KEY_LEFTMETA" if sys.platform == "darwin" else "KEY_SCROLLLOCK"
        assert config.key == expected_key
        assert config.device == ""

    def test_output_config_defaults(self) -> None:
        """Test OutputConfig has correct defaults."""
        config = OutputConfig()
        assert config.method == "keyboard"
        assert config.typing_delay_ms == 5
        assert config.auto_enter is False

    def test_command_config_defaults(self) -> None:
        """Test CommandConfig has correct defaults."""
        config = CommandConfig()
        assert config.enabled is True
        assert config.ollama_timeout == 5.0

    def test_full_config_defaults(self) -> None:
        """Test Config has all sub-configs with defaults."""
        config = Config()
        assert isinstance(config.audio, AudioConfig)
        assert isinstance(config.stt, STTConfig)
        assert isinstance(config.hotkey, HotkeyConfig)
        assert isinstance(config.output, OutputConfig)
        assert isinstance(config.command, CommandConfig)


class TestConfigLoading:
    """Test configuration file loading."""

    def test_load_nonexistent_file(self) -> None:
        """Test loading from nonexistent file returns defaults."""
        config = load_config(Path("/nonexistent/path/config.toml"))
        assert config is not None
        assert config.audio.sample_rate == 16000

    def test_load_empty_toml(self) -> None:
        """Test loading from empty TOML file returns defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config is not None
            assert config.stt.model == "large-v3-turbo"
        finally:
            temp_path.unlink()

    def test_load_partial_toml(self) -> None:
        """Test loading TOML with partial config merges with defaults."""
        toml_content = """
[stt]
model = "base"
language = "en"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.stt.model == "base"
            assert config.stt.language == "en"
            # Other values should be defaults
            assert config.stt.device == "auto"
            assert config.audio.sample_rate == 16000
        finally:
            temp_path.unlink()
