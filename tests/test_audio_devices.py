"""Tests for audio device selection feature."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from dictare.config import AudioConfig, load_config


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
        from dictare.core.audio_manager import AudioManager

        cfg = AudioConfig(input_device="My USB Mic")

        with patch("dictare.core.audio_manager.AudioCapture") as mock_capture, \
             patch("dictare.audio.device_monitor.create_device_monitor"), \
             patch("dictare.audio.vad.SileroVAD"), \
             patch("dictare.audio.vad.StreamingVAD"):
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
        from dictare.core.audio_manager import AudioManager

        cfg = AudioConfig()
        cfg.advanced.device = "Legacy Device"

        with patch("dictare.core.audio_manager.AudioCapture") as mock_capture, \
             patch("dictare.audio.device_monitor.create_device_monitor"), \
             patch("dictare.audio.vad.SileroVAD"), \
             patch("dictare.audio.vad.StreamingVAD"):
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
        from dictare.core.engine import DictareEngine

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
        config.output.auto_submit = True
        config.hotkey.key = "F18"
        config.hotkey.device = None
        config.keyboard.shortcuts = {}
        config.stats.typing_wpm = 40
        config.tts.engine = "espeak"
        config.tts.language = "en"
        config.pipeline.enabled = False

        engine = DictareEngine(config=config)
        status = engine.get_status()

        assert "audio_devices" in status["platform"]
        assert status["platform"]["audio_devices"]["input"] == "(default)"
        assert status["platform"]["audio_devices"]["output"] == "(default)"

    def test_status_shows_configured_devices(self) -> None:
        """get_status() shows configured device names."""
        from dictare.core.engine import DictareEngine

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
        config.output.auto_submit = True
        config.hotkey.key = "F18"
        config.hotkey.device = None
        config.keyboard.shortcuts = {}
        config.stats.typing_wpm = 40
        config.tts.engine = "espeak"
        config.tts.language = "en"
        config.pipeline.enabled = False

        engine = DictareEngine(config=config)
        status = engine.get_status()

        assert status["platform"]["audio_devices"]["input"] == "Blue Yeti"
        assert status["platform"]["audio_devices"]["output"] == "AirPods Pro"


class TestBeepOutputDevice:
    """Test beep module output device wiring."""

    def test_set_output_device(self) -> None:
        """set_output_device sets the module-level device."""
        from dictare.audio import beep

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


class TestReconnectReason:
    """Test AudioCapture.reconnect_reason property."""

    def test_no_stream_returns_none(self) -> None:
        """No stream → None (healthy)."""
        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        assert cap.reconnect_reason is None

    def test_fresh_stream_returns_none(self) -> None:
        """Active stream with recent callback → None."""
        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._stream = MagicMock(active=True)
        cap._last_callback_time = time.monotonic()
        assert cap.reconnect_reason is None

    def test_callback_error(self) -> None:
        """_needs_reconnect flag → 'callback_error'."""
        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._needs_reconnect = True
        assert cap.reconnect_reason == "callback_error"

    def test_stream_inactive(self) -> None:
        """Stream exists but not active → 'stream_inactive'."""
        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._stream = MagicMock(active=False)
        assert cap.reconnect_reason == "stream_inactive"

    def test_stream_stale(self) -> None:
        """Active stream with no data for >3s → 'stream_stale'."""
        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._stream = MagicMock(active=True)
        cap._last_callback_time = time.monotonic() - 5.0
        assert cap.reconnect_reason == "stream_stale"

    def test_inactive_stream_not_stale(self) -> None:
        """Inactive stream returns 'stream_inactive', not 'stream_stale'."""
        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._stream = MagicMock(active=False)
        cap._last_callback_time = time.monotonic() - 10.0
        assert cap.reconnect_reason == "stream_inactive"

    def test_streaming_callback_updates_timestamp(self) -> None:
        """_streaming_audio_callback updates _last_callback_time."""
        import numpy as np

        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._streaming_callback = MagicMock()
        old_time = cap._last_callback_time

        # Simulate a callback with no status flags
        status = MagicMock()
        status.__bool__ = lambda s: False
        indata = np.zeros((512, 1), dtype=np.float32)
        cap._streaming_audio_callback(indata, 512, {}, status)

        assert cap._last_callback_time > old_time

    def test_streaming_callback_resets_error_count(self) -> None:
        """Successful callback resets _callback_error_count."""
        import numpy as np

        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._streaming_callback = MagicMock()
        cap._callback_error_count = 2

        status = MagicMock()
        status.__bool__ = lambda s: False
        indata = np.zeros((512, 1), dtype=np.float32)
        cap._streaming_audio_callback(indata, 512, {}, status)

        assert cap._callback_error_count == 0

    def test_consecutive_errors_below_threshold(self) -> None:
        """Errors below threshold don't trigger reconnect."""
        import numpy as np

        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._streaming_callback = MagicMock()

        # Simulate error status (not input_overflow)
        status = MagicMock()
        status.__bool__ = lambda s: True
        status.input_overflow = False
        indata = np.zeros((512, 1), dtype=np.float32)

        # 2 errors (below threshold of 3) — no reconnect
        cap._streaming_audio_callback(indata, 512, {}, status)
        cap._streaming_audio_callback(indata, 512, {}, status)
        assert cap._callback_error_count == 2
        assert not cap._needs_reconnect

    def test_consecutive_errors_at_threshold(self) -> None:
        """Errors at threshold trigger reconnect."""
        import numpy as np

        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._streaming_callback = MagicMock()

        status = MagicMock()
        status.__bool__ = lambda s: True
        status.input_overflow = False
        indata = np.zeros((512, 1), dtype=np.float32)

        for _ in range(3):
            cap._streaming_audio_callback(indata, 512, {}, status)

        assert cap._callback_error_count == 3
        assert cap._needs_reconnect

    def test_wait_for_audio_success(self) -> None:
        """wait_for_audio returns True when callback timestamp advances."""
        import threading

        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._last_callback_time = time.monotonic()

        def bump() -> None:
            time.sleep(0.05)
            cap._last_callback_time = time.monotonic()

        threading.Thread(target=bump, daemon=True).start()
        assert cap.wait_for_audio(timeout_s=1.0) is True

    def test_wait_for_audio_timeout(self) -> None:
        """wait_for_audio returns False when no callback arrives."""
        from dictare.audio.capture import AudioCapture

        cap = AudioCapture()
        cap._last_callback_time = time.monotonic()
        assert cap.wait_for_audio(timeout_s=0.15) is False


class TestAudioManagerReconnectReason:
    """Test AudioManager.reconnect_reason delegates to AudioCapture."""

    def test_delegates_to_capture(self) -> None:
        """reconnect_reason delegates to AudioCapture.reconnect_reason."""
        from dictare.core.audio_manager import AudioManager

        cfg = AudioConfig()
        manager = AudioManager(config=cfg)
        manager._audio = MagicMock()
        manager._audio.reconnect_reason = "stream_stale"
        assert manager.reconnect_reason == "stream_stale"

    def test_no_audio_returns_none(self) -> None:
        """reconnect_reason returns None when no audio capture."""
        from dictare.core.audio_manager import AudioManager

        cfg = AudioConfig()
        manager = AudioManager(config=cfg)
        assert manager.reconnect_reason is None


class TestCircuitBreaker:
    """Test AudioManager reconnect circuit breaker."""

    def test_circuit_breaker_trips(self) -> None:
        """Reconnect fails after too many attempts in window."""
        from dictare.core.audio_manager import AudioManager

        cfg = AudioConfig()
        manager = AudioManager(config=cfg)
        manager._audio = MagicMock()

        # Fill up the reconnect timestamps to trip circuit breaker
        now = time.monotonic()
        manager._reconnect_timestamps = [now - i for i in range(5)]

        result = manager.reconnect(MagicMock())
        assert result is False

    def test_old_timestamps_pruned(self) -> None:
        """Timestamps older than window are pruned."""
        from dictare.core.audio_manager import AudioManager

        cfg = AudioConfig()
        manager = AudioManager(config=cfg)

        # Add old timestamps outside the window
        old = time.monotonic() - 120.0
        manager._reconnect_timestamps = [old - i for i in range(5)]

        # Should NOT trip circuit breaker (all old)
        # Will fail on actual reconnect (no audio), but circuit breaker won't block
        manager._audio = MagicMock()
        with patch.object(manager, "_reinit_portaudio"), \
             patch("dictare.core.audio_manager.AudioCapture"), \
             patch("time.sleep"):
                # Let it fail naturally (no real device)
                manager.reconnect(MagicMock())
        # Old timestamps should be pruned
        assert all(
            time.monotonic() - t < AudioManager._RECONNECT_WINDOW_S
            for t in manager._reconnect_timestamps
        )
