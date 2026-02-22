"""Tests for audio device selection feature."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from voxtype.config import AudioConfig, load_config


class TestAudioDeviceConfig:
    """Test AudioConfig input_device and output_device fields."""

    def test_default_empty_strings(self) -> None:
        """Default input/output device is empty string (system default)."""
        cfg = AudioConfig()
        assert cfg.input_device == ""
        assert cfg.output_device == ""

    def test_migration_from_advanced_device(self) -> None:
        """audio.advanced.device is migrated to audio.input_device."""
        cfg = AudioConfig.model_validate({
            "advanced": {"device": "My USB Mic"},
        })
        assert cfg.input_device == "My USB Mic"
        assert cfg.advanced.device is None

    def test_migration_does_not_overwrite_explicit(self) -> None:
        """Migration skips if input_device is already set."""
        cfg = AudioConfig.model_validate({
            "input_device": "Blue Yeti",
            "advanced": {"device": "My USB Mic"},
        })
        assert cfg.input_device == "Blue Yeti"
        # advanced.device is NOT cleared (user explicitly set both)
        assert cfg.advanced.device == "My USB Mic"

    def test_migration_from_toml(self) -> None:
        """TOML config with [audio.advanced] device= migrates correctly."""
        toml_content = """
[audio]

[audio.advanced]
device = "MacBook Pro Microphone"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.audio.input_device == "MacBook Pro Microphone"
            assert config.audio.advanced.device is None
        finally:
            temp_path.unlink()

    def test_explicit_input_output_from_toml(self) -> None:
        """TOML config with explicit input_device and output_device."""
        toml_content = """
[audio]
input_device = "Blue Yeti"
output_device = "AirPods Pro"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.audio.input_device == "Blue Yeti"
            assert config.audio.output_device == "AirPods Pro"
        finally:
            temp_path.unlink()


class TestAudioManagerDeviceWiring:
    """Test AudioManager uses input_device config."""

    def test_initialize_uses_input_device(self) -> None:
        """AudioManager.initialize() passes input_device to AudioCapture."""
        from voxtype.core.audio_manager import AudioManager

        cfg = AudioConfig(input_device="My USB Mic")

        with patch("voxtype.core.audio_manager.AudioCapture") as mock_capture, \
             patch("voxtype.audio.device_monitor.create_device_monitor"), \
             patch("voxtype.audio.vad.SileroVAD"), \
             patch("voxtype.audio.vad.StreamingVAD"):
            manager = AudioManager(config=cfg)
            manager.initialize(
                on_speech_start=lambda: None,
                on_speech_end=lambda x: None,
                on_max_speech=lambda: None,
                headless=True,
            )
            mock_capture.assert_called_once_with(
                sample_rate=16000,
                channels=1,
                device="My USB Mic",
            )

    def test_initialize_falls_back_to_advanced_device(self) -> None:
        """When input_device is empty, advanced.device is used."""
        from voxtype.core.audio_manager import AudioManager

        cfg = AudioConfig()
        cfg.advanced.device = "Legacy Device"

        with patch("voxtype.core.audio_manager.AudioCapture") as mock_capture, \
             patch("voxtype.audio.device_monitor.create_device_monitor"), \
             patch("voxtype.audio.vad.SileroVAD"), \
             patch("voxtype.audio.vad.StreamingVAD"):
            manager = AudioManager(config=cfg)
            manager.initialize(
                on_speech_start=lambda: None,
                on_speech_end=lambda x: None,
                on_max_speech=lambda: None,
                headless=True,
            )
            mock_capture.assert_called_once_with(
                sample_rate=16000,
                channels=1,
                device="Legacy Device",
            )


class TestEngineStatusAudioDevices:
    """Test engine status includes audio_devices."""

    def test_status_contains_audio_devices_default(self) -> None:
        """get_status() includes audio_devices with defaults."""
        from voxtype.core.engine import VoxtypeEngine

        config = MagicMock()
        config.verbose = False
        config.stt.hw_accel = False
        config.stt.model = "tiny"
        config.stt.advanced.device = "cpu"
        config.stt.advanced.compute_type = "int8"
        config.stt.language = "en"
        config.stt.advanced.hotwords = ""
        config.stt.advanced.beam_size = 5
        config.stt.advanced.max_repetitions = 3
        config.audio.silence_ms = 1200
        config.audio.max_duration = 30
        config.audio.audio_feedback = False
        config.audio.headphones_mode = True
        config.audio.input_device = ""
        config.audio.output_device = ""
        config.output.mode = "keyboard"
        config.output.typing_delay_ms = 0
        config.output.auto_enter = True
        config.hotkey.key = "F18"
        config.hotkey.device = None
        config.keyboard.shortcuts = {}
        config.stats.typing_wpm = 40
        config.tts.engine = "espeak"
        config.tts.language = "en"
        config.pipeline.enabled = False

        engine = VoxtypeEngine(config=config)
        status = engine.get_status()

        assert "audio_devices" in status["platform"]
        assert status["platform"]["audio_devices"]["input"] == "(default)"
        assert status["platform"]["audio_devices"]["output"] == "(default)"

    def test_status_shows_configured_devices(self) -> None:
        """get_status() shows configured device names."""
        from voxtype.core.engine import VoxtypeEngine

        config = MagicMock()
        config.verbose = False
        config.stt.hw_accel = False
        config.stt.model = "tiny"
        config.stt.advanced.device = "cpu"
        config.stt.advanced.compute_type = "int8"
        config.stt.language = "en"
        config.stt.advanced.hotwords = ""
        config.stt.advanced.beam_size = 5
        config.stt.advanced.max_repetitions = 3
        config.audio.silence_ms = 1200
        config.audio.max_duration = 30
        config.audio.audio_feedback = False
        config.audio.headphones_mode = True
        config.audio.input_device = "Blue Yeti"
        config.audio.output_device = "AirPods Pro"
        config.output.mode = "keyboard"
        config.output.typing_delay_ms = 0
        config.output.auto_enter = True
        config.hotkey.key = "F18"
        config.hotkey.device = None
        config.keyboard.shortcuts = {}
        config.stats.typing_wpm = 40
        config.tts.engine = "espeak"
        config.tts.language = "en"
        config.pipeline.enabled = False

        engine = VoxtypeEngine(config=config)
        status = engine.get_status()

        assert status["platform"]["audio_devices"]["input"] == "Blue Yeti"
        assert status["platform"]["audio_devices"]["output"] == "AirPods Pro"


class TestBeepOutputDevice:
    """Test beep module output device wiring."""

    def test_set_output_device(self) -> None:
        """set_output_device sets the module-level device."""
        from voxtype.audio import beep

        old = beep._output_device
        try:
            beep.set_output_device("AirPods Pro")
            assert beep._output_device == "AirPods Pro"

            beep.set_output_device("")
            assert beep._output_device is None

            beep.set_output_device(None)
            assert beep._output_device is None
        finally:
            beep._output_device = old
