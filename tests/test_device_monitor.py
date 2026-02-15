"""Tests for audio device change monitor."""

from __future__ import annotations

import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from voxtype.audio.capture import AudioCapture
from voxtype.audio.device_monitor import (
    CoreAudioDeviceMonitor,
    DeviceMonitor,
    PollingDeviceMonitor,
    create_device_monitor,
)

# =============================================================================
# Helper
# =============================================================================


def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    """Poll predicate until True or timeout."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise TimeoutError("Predicate not satisfied within timeout")


# =============================================================================
# Factory
# =============================================================================


class TestCreateDeviceMonitor:
    """Test platform-based factory function."""

    def test_returns_coreaudio_on_darwin(self) -> None:
        with patch("voxtype.audio.device_monitor.sys") as mock_sys:
            mock_sys.platform = "darwin"
            monitor = create_device_monitor(lambda: None)
            assert isinstance(monitor, CoreAudioDeviceMonitor)

    def test_returns_polling_on_linux(self) -> None:
        with patch("voxtype.audio.device_monitor.sys") as mock_sys:
            mock_sys.platform = "linux"
            monitor = create_device_monitor(lambda: None)
            assert isinstance(monitor, PollingDeviceMonitor)

    def test_returns_polling_on_unknown(self) -> None:
        with patch("voxtype.audio.device_monitor.sys") as mock_sys:
            mock_sys.platform = "win32"
            monitor = create_device_monitor(lambda: None)
            assert isinstance(monitor, PollingDeviceMonitor)

    def test_all_subclass_device_monitor(self) -> None:
        assert issubclass(CoreAudioDeviceMonitor, DeviceMonitor)
        assert issubclass(PollingDeviceMonitor, DeviceMonitor)


# =============================================================================
# PollingDeviceMonitor
# =============================================================================


class TestPollingDeviceMonitor:
    """Test the polling fallback device monitor."""

    def test_start_stop(self) -> None:
        monitor = PollingDeviceMonitor(on_device_change=lambda: None)
        monitor.POLL_INTERVAL = 0.05
        monitor.start()
        assert monitor.running
        monitor.stop()
        assert not monitor.running

    def test_start_idempotent(self) -> None:
        monitor = PollingDeviceMonitor(on_device_change=lambda: None)
        monitor.POLL_INTERVAL = 0.05
        monitor.start()
        monitor.start()  # Should not raise or create second thread
        assert monitor.running
        monitor.stop()

    def test_stop_idempotent(self) -> None:
        monitor = PollingDeviceMonitor(on_device_change=lambda: None)
        monitor.stop()  # Not started, should not raise
        assert not monitor.running

    def test_detects_device_change(self) -> None:
        changes: list[int] = []
        monitor = PollingDeviceMonitor(on_device_change=lambda: changes.append(1))
        monitor.POLL_INTERVAL = 0.02

        device_sequence = iter([0, 0, 1, 1, 1])

        with patch.object(
            PollingDeviceMonitor,
            "_get_default_input_device",
            side_effect=device_sequence,
        ):
            monitor._last_device = 0  # Set initial state
            monitor._stop_event.clear()
            monitor._running = True
            # Run a few poll iterations manually
            monitor._poll_loop.__wrapped__ if hasattr(monitor._poll_loop, "__wrapped__") else None

            # Use the thread-based approach
            monitor._thread = threading.Thread(target=monitor._poll_loop, daemon=True)
            monitor._thread.start()

            _wait_until(lambda: len(changes) > 0, timeout=1.0)
            monitor._stop_event.set()
            monitor._thread.join(timeout=1.0)

        assert len(changes) >= 1

    def test_no_callback_when_device_unchanged(self) -> None:
        changes: list[int] = []
        monitor = PollingDeviceMonitor(on_device_change=lambda: changes.append(1))
        monitor.POLL_INTERVAL = 0.02

        with patch.object(
            PollingDeviceMonitor,
            "_get_default_input_device",
            return_value=0,
        ):
            monitor._last_device = 0
            monitor._stop_event.clear()
            monitor._running = True
            monitor._thread = threading.Thread(target=monitor._poll_loop, daemon=True)
            monitor._thread.start()

            # Let it poll a few times
            import time

            time.sleep(0.1)
            monitor._stop_event.set()
            monitor._thread.join(timeout=1.0)

        assert len(changes) == 0

    def test_callback_on_query_failure(self) -> None:
        """When query_devices fails, treat it as device change."""
        changes: list[int] = []
        monitor = PollingDeviceMonitor(on_device_change=lambda: changes.append(1))
        monitor.POLL_INTERVAL = 0.02

        with patch.object(
            PollingDeviceMonitor,
            "_get_default_input_device",
            side_effect=Exception("PortAudio error"),
        ):
            monitor._last_device = 0
            monitor._stop_event.clear()
            monitor._running = True
            monitor._thread = threading.Thread(target=monitor._poll_loop, daemon=True)
            monitor._thread.start()

            _wait_until(lambda: len(changes) > 0, timeout=1.0)
            monitor._stop_event.set()
            monitor._thread.join(timeout=1.0)

        assert len(changes) >= 1


# =============================================================================
# CoreAudioDeviceMonitor
# =============================================================================


class TestCoreAudioDeviceMonitor:
    """Test CoreAudio device monitor."""

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_install_and_remove_listener(self) -> None:
        monitor = CoreAudioDeviceMonitor(on_device_change=lambda: None)
        monitor.start()
        assert monitor.running
        assert monitor._listener_installed
        monitor.stop()
        assert not monitor._listener_installed
        assert not monitor.running

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_start_idempotent(self) -> None:
        monitor = CoreAudioDeviceMonitor(on_device_change=lambda: None)
        monitor.start()
        monitor.start()  # Should not install twice
        assert monitor._listener_installed
        monitor.stop()

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_stop_idempotent(self) -> None:
        monitor = CoreAudioDeviceMonitor(on_device_change=lambda: None)
        monitor.stop()  # Not started, should not raise

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_callback_ref_kept(self) -> None:
        """Ctypes callback reference must not be garbage collected."""
        monitor = CoreAudioDeviceMonitor(on_device_change=lambda: None)
        monitor.start()
        assert monitor._callback_ref is not None
        monitor.stop()


# =============================================================================
# AudioCapture.emergency_abort()
# =============================================================================


class TestEmergencyAbort:
    """Test AudioCapture.emergency_abort() method."""

    def test_sets_needs_reconnect(self) -> None:
        capture = AudioCapture()
        assert not capture.needs_reconnect()
        capture.emergency_abort()
        assert capture.needs_reconnect()

    def test_aborts_active_stream(self) -> None:
        capture = AudioCapture()
        mock_stream = MagicMock()
        capture._stream = mock_stream
        capture.emergency_abort()
        mock_stream.abort.assert_called_once()
        assert capture._needs_reconnect

    def test_safe_when_no_stream(self) -> None:
        capture = AudioCapture()
        capture._stream = None
        capture.emergency_abort()  # Should not raise
        assert capture._needs_reconnect

    def test_safe_when_abort_raises(self) -> None:
        capture = AudioCapture()
        mock_stream = MagicMock()
        mock_stream.abort.side_effect = Exception("stream dead")
        capture._stream = mock_stream
        capture.emergency_abort()  # Should not raise
        assert capture._needs_reconnect

    def test_idempotent(self) -> None:
        capture = AudioCapture()
        mock_stream = MagicMock()
        capture._stream = mock_stream
        capture.emergency_abort()
        capture.emergency_abort()
        assert capture._needs_reconnect
        assert mock_stream.abort.call_count == 2


# =============================================================================
# AudioManager integration
# =============================================================================


class TestAudioManagerDeviceMonitor:
    """Test AudioManager device monitor integration."""

    def test_on_device_change_calls_emergency_abort(self) -> None:
        """Device change callback triggers emergency_abort on AudioCapture."""
        from voxtype.core.audio_manager import AudioManager

        config = MagicMock()
        config.sample_rate = 16000
        config.channels = 1
        config.device = None
        config.silence_ms = 1200
        config.min_speech_ms = 100
        config.max_duration = 60
        config.pre_buffer_ms = 640

        manager = AudioManager(config=config)
        mock_audio = MagicMock(spec=AudioCapture)
        manager._audio = mock_audio

        manager._on_device_change()
        mock_audio.emergency_abort.assert_called_once()

    def test_on_device_change_safe_without_audio(self) -> None:
        """Device change when _audio is None should not raise."""
        from voxtype.core.audio_manager import AudioManager

        config = MagicMock()
        manager = AudioManager(config=config)
        manager._audio = None
        manager._on_device_change()  # Should not raise

    def test_close_stops_device_monitor(self) -> None:
        """AudioManager.close() stops the device monitor."""
        from voxtype.core.audio_manager import AudioManager

        config = MagicMock()
        manager = AudioManager(config=config)
        mock_monitor = MagicMock(spec=DeviceMonitor)
        manager._device_monitor = mock_monitor

        manager.close()
        mock_monitor.stop.assert_called_once()
        assert manager._device_monitor is None
