"""Tests for configuration module."""

import tempfile
from pathlib import Path

from dictare.config import (
    AudioConfig,
    Config,
    HotkeyConfig,
    OutputConfig,
    SoundConfig,
    STTConfig,
    load_config,
    load_raw_values,
)


class TestConfigDefaults:
    """Test default configuration values."""

    def test_audio_config_defaults(self) -> None:
        """Test AudioConfig has correct defaults."""
        config = AudioConfig()
        assert config.advanced.sample_rate == 16000
        assert config.advanced.channels == 1
        assert config.advanced.device is None
        assert config.audio_feedback is True

    def test_stt_config_defaults(self) -> None:
        """Test STTConfig has correct defaults."""
        config = STTConfig()
        assert config.model == "large-v3-turbo"
        assert config.language == "auto"
        assert config.advanced.device == "auto"
        assert config.advanced.compute_type == "int8"
        assert config.advanced.beam_size == 5

    def test_hotkey_config_defaults(self) -> None:
        """Test HotkeyConfig has correct defaults."""
        import sys
        config = HotkeyConfig()
        # Platform-specific: Command on macOS, Scroll Lock on Linux
        expected_key = "KEY_RIGHTMETA" if sys.platform == "darwin" else "KEY_SCROLLLOCK"
        assert config.key == expected_key
        assert config.device == ""

    def test_output_config_defaults(self) -> None:
        """Test OutputConfig has correct defaults."""
        config = OutputConfig()
        assert config.mode == "agents"
        assert config.typing_delay_ms == 2
        assert config.auto_submit is False

    def test_full_config_defaults(self) -> None:
        """Test Config has all sub-configs with defaults."""
        config = Config()
        assert isinstance(config.audio, AudioConfig)
        assert isinstance(config.stt, STTConfig)
        assert isinstance(config.hotkey, HotkeyConfig)
        assert isinstance(config.output, OutputConfig)


class TestConfigLoading:
    """Test configuration file loading."""

    def test_load_nonexistent_file(self) -> None:
        """Test loading from nonexistent file returns defaults."""
        config = load_config(Path("/nonexistent/path/config.toml"))
        assert config is not None
        assert config.audio.advanced.sample_rate == 16000

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
            assert config.stt.advanced.device == "auto"
            assert config.audio.advanced.sample_rate == 16000
        finally:
            temp_path.unlink()


class TestLoadRawValues:
    """Test load_raw_values returns only explicitly set TOML keys."""

    def test_empty_file_returns_empty_dict(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("")
            temp_path = Path(f.name)
        try:
            assert load_raw_values(temp_path) == {}
        finally:
            temp_path.unlink()

    def test_nonexistent_file_returns_empty_dict(self) -> None:
        assert load_raw_values(Path("/nonexistent/config.toml")) == {}

    def test_flat_keys(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("verbose = true\n")
            temp_path = Path(f.name)
        try:
            raw = load_raw_values(temp_path)
            assert raw == {"verbose": True}
        finally:
            temp_path.unlink()

    def test_nested_keys_flattened(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[stt]\nmodel = "base"\nlanguage = "it"\n')
            temp_path = Path(f.name)
        try:
            raw = load_raw_values(temp_path)
            assert raw == {"stt.model": "base", "stt.language": "it"}
        finally:
            temp_path.unlink()

    def test_only_explicit_keys_no_defaults(self) -> None:
        """Only keys in the TOML file appear — no Pydantic defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[stt]\nmodel = "base"\n')
            temp_path = Path(f.name)
        try:
            raw = load_raw_values(temp_path)
            assert "stt.model" in raw
            assert "stt.language" not in raw  # Not in TOML → not in raw
            assert "output.mode" not in raw
        finally:
            temp_path.unlink()

    def test_deeply_nested(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[stt.advanced]\nbeam_size = 3\n')
            temp_path = Path(f.name)
        try:
            raw = load_raw_values(temp_path)
            assert raw == {"stt.advanced.beam_size": 3}
        finally:
            temp_path.unlink()


class TestSoundConfig:
    """Test per-event sound configuration with TOML sub-tables."""

    def test_defaults_sound_events(self) -> None:
        """All 6 sound events present; transcribing disabled by default."""
        cfg = AudioConfig()
        expected = {"start", "stop", "transcribing", "ready", "sent", "agent_announce"}
        assert set(cfg.sounds.keys()) == expected
        # Transcribing disabled by default (continuous VAD makes it unnecessary)
        assert cfg.sounds["transcribing"].enabled is False
        # All others enabled
        for name in ("start", "stop", "ready", "sent", "agent_announce"):
            assert cfg.sounds[name].enabled is True
        for sc in cfg.sounds.values():
            assert sc.path is None

    def test_toml_subtable_parsing(self) -> None:
        """TOML sub-tables parse into SoundConfig correctly."""
        toml_content = """
[audio]
audio_feedback = true

[audio.sounds.start]
enabled = true
path = "/custom/start.mp3"

[audio.sounds.transcribing]
enabled = false
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.audio.sounds["start"].enabled is True
            assert config.audio.sounds["start"].path == "/custom/start.mp3"
            assert config.audio.sounds["transcribing"].enabled is False
        finally:
            temp_path.unlink()

    def test_backward_compat_no_sounds_section(self) -> None:
        """Config without [audio.sounds.*] uses defaults."""
        toml_content = """
[audio]
audio_feedback = true
silence_ms = 1000
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.audio.audio_feedback is True
            assert len(config.audio.sounds) == 6
            assert config.audio.sounds["start"].enabled is True
        finally:
            temp_path.unlink()

    def test_get_sound_for_event_enabled(self) -> None:
        """get_sound_for_event returns (True, path) when enabled."""
        from dictare.audio.beep import DEFAULT_SOUND_START, get_sound_for_event

        cfg = AudioConfig()
        enabled, path = get_sound_for_event(cfg, "start")
        assert enabled is True
        assert path == str(DEFAULT_SOUND_START)

    def test_get_sound_for_event_disabled(self) -> None:
        """get_sound_for_event returns (False, '') when event disabled."""
        from dictare.audio.beep import get_sound_for_event

        cfg = AudioConfig()
        cfg.sounds["start"] = SoundConfig(enabled=False)
        enabled, path = get_sound_for_event(cfg, "start")
        assert enabled is False

    def test_get_sound_for_event_custom_path(self) -> None:
        """get_sound_for_event returns custom path when set."""
        from dictare.audio.beep import get_sound_for_event

        cfg = AudioConfig()
        cfg.sounds["stop"] = SoundConfig(enabled=True, path="/my/custom.mp3")
        enabled, path = get_sound_for_event(cfg, "stop")
        assert enabled is True
        assert path == "/my/custom.mp3"

    def test_get_sound_for_event_master_switch_off(self) -> None:
        """Master switch audio_feedback=false disables all sounds."""
        from dictare.audio.beep import get_sound_for_event

        cfg = AudioConfig(audio_feedback=False)
        for name in ("start", "stop", "transcribing", "ready", "sent", "agent_announce"):
            enabled, _ = get_sound_for_event(cfg, name)
            assert enabled is False

    def test_get_sound_for_event_agent_announce(self) -> None:
        """agent_announce returns (True, '') since it uses TTS not a file."""
        from dictare.audio.beep import get_sound_for_event

        cfg = AudioConfig()
        enabled, path = get_sound_for_event(cfg, "agent_announce")
        assert enabled is True
        assert path == ""
