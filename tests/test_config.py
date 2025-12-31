"""Tests for configuration module."""

import tempfile
from pathlib import Path

import pytest

from voxtype.config import (
    AudioConfig,
    CommandConfig,
    Config,
    HotkeyConfig,
    InjectionConfig,
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
        assert config.backend == "faster-whisper"
        assert config.model_size == "large-v3-turbo"
        assert config.language == "auto"
        assert config.device == "cpu"

    def test_hotkey_config_defaults(self) -> None:
        """Test HotkeyConfig has correct defaults."""
        config = HotkeyConfig()
        assert config.backend == "auto"
        assert config.key == "KEY_SCROLLLOCK"

    def test_injection_config_defaults(self) -> None:
        """Test InjectionConfig has correct defaults."""
        config = InjectionConfig()
        assert config.backend == "auto"
        assert config.auto_enter is True
        assert config.fallback_to_clipboard is True

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
        assert isinstance(config.injection, InjectionConfig)
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
            assert config.stt.model_size == "large-v3-turbo"
        finally:
            temp_path.unlink()

    def test_load_partial_toml(self) -> None:
        """Test loading TOML with partial config merges with defaults."""
        toml_content = """
[stt]
model_size = "base"
language = "en"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.stt.model_size == "base"
            assert config.stt.language == "en"
            # Other values should be defaults
            assert config.stt.backend == "faster-whisper"
            assert config.audio.sample_rate == 16000
        finally:
            temp_path.unlink()
