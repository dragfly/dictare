"""Tests for audio device change monitor."""

from __future__ import annotations

import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from dictare.audio.capture import AudioCapture
from dictare.audio.device_monitor import (
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
        with patch("dictare.audio.device_monitor.sys") as mock_sys:
            mock_sys.platform = "darwin"
            monitor = create_device_monitor(lambda _reason: None)
            assert isinstance(monitor, CoreAudioDeviceMonitor)

    def test_returns_polling_on_linux(self) -> None:
        with patch("dictare.audio.device_monitor.sys") as mock_sys:
            mock_sys.platform = "linux"
            monitor = create_device_monitor(lambda _reason: None)
            assert isinstance(monitor, PollingDeviceMonitor)

    def test_returns_polling_on_unknown(self) -> None:
        with patch("dictare.audio.device_monitor.sys") as mock_sys:
            mock_sys.platform = "win32"
            monitor = create_device_monitor(lambda _reason: None)
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
        monitor = PollingDeviceMonitor(on_device_change=lambda _reason: None)
        monitor.POLL_INTERVAL = 0.05
        monitor.start()
        assert monitor.running
        monitor.stop()
        assert not monitor.running

    def test_start_idempotent(self) -> None:
        monitor = PollingDeviceMonitor(on_device_change=lambda _reason: None)
        monitor.POLL_INTERVAL = 0.05
        monitor.start()
        monitor.start()  # Should not raise or create second thread
        assert monitor.running
        monitor.stop()

    def test_stop_idempotent(self) -> None:
        monitor = PollingDeviceMonitor(on_device_change=lambda _reason: None)
        monitor.stop()  # Not started, should not raise
        assert not monitor.running

    def test_detects_device_change(self) -> None:
        changes: list[str] = []
        monitor = PollingDeviceMonitor(on_device_change=lambda reason: changes.append(reason))
        monitor.POLL_INTERVAL = 0.02

        # Simulate default input changing: (input=0, output=0, count=2) -> (input=1, output=0, count=2)
        snapshot_sequence = iter([(0, 0, 2), (1, 0, 2), (1, 0, 2)])

        with patch.object(
            PollingDeviceMonitor,
            "_snapshot",
            side_effect=snapshot_sequence,
        ):
            monitor._last_input = 0
            monitor._last_output = 0
            monitor._last_count = 2
            monitor._stop_event.clear()
            monitor._running = True

            monitor._thread = threading.Thread(target=monitor._poll_loop, daemon=True)
            monitor._thread.start()

            _wait_until(lambda: len(changes) > 0, timeout=1.0)
            monitor._stop_event.set()
            monitor._thread.join(timeout=1.0)

        assert len(changes) >= 1
        assert changes[0] == "default_input_changed"

    def test_no_callback_when_device_unchanged(self) -> None:
        changes: list[str] = []
        monitor = PollingDeviceMonitor(on_device_change=lambda reason: changes.append(reason))
        monitor.POLL_INTERVAL = 0.02

        with patch.object(
            PollingDeviceMonitor,
            "_snapshot",
            return_value=(0, 0, 2),
        ):
            monitor._last_input = 0
            monitor._last_output = 0
            monitor._last_count = 2
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
        changes: list[str] = []
        monitor = PollingDeviceMonitor(on_device_change=lambda reason: changes.append(reason))
        monitor.POLL_INTERVAL = 0.02

        with patch.object(
            PollingDeviceMonitor,
            "_snapshot",
            side_effect=Exception("PortAudio error"),
        ):
            monitor._last_input = 0
            monitor._last_output = 0
            monitor._last_count = 2
            monitor._stop_event.clear()
            monitor._running = True
            monitor._thread = threading.Thread(target=monitor._poll_loop, daemon=True)
            monitor._thread.start()

            _wait_until(lambda: len(changes) > 0, timeout=1.0)
            monitor._stop_event.set()
            monitor._thread.join(timeout=1.0)

        assert len(changes) >= 1
        assert changes[0] == "devices_changed"

    def test_detects_output_change(self) -> None:
        changes: list[str] = []
        monitor = PollingDeviceMonitor(on_device_change=lambda reason: changes.append(reason))
        monitor.POLL_INTERVAL = 0.02

        snapshot_sequence = iter([(0, 0, 2), (0, 1, 2), (0, 1, 2)])

        with patch.object(
            PollingDeviceMonitor,
            "_snapshot",
            side_effect=snapshot_sequence,
        ):
            monitor._last_input = 0
            monitor._last_output = 0
            monitor._last_count = 2
            monitor._stop_event.clear()
            monitor._running = True

            monitor._thread = threading.Thread(target=monitor._poll_loop, daemon=True)
            monitor._thread.start()

            _wait_until(lambda: len(changes) > 0, timeout=1.0)
            monitor._stop_event.set()
            monitor._thread.join(timeout=1.0)

        assert len(changes) >= 1
        assert changes[0] == "default_output_changed"

    def test_detects_device_count_change(self) -> None:
        changes: list[str] = []
        monitor = PollingDeviceMonitor(on_device_change=lambda reason: changes.append(reason))
        monitor.POLL_INTERVAL = 0.02

        snapshot_sequence = iter([(0, 0, 2), (0, 0, 3), (0, 0, 3)])

        with patch.object(
            PollingDeviceMonitor,
            "_snapshot",
            side_effect=snapshot_sequence,
        ):
            monitor._last_input = 0
            monitor._last_output = 0
            monitor._last_count = 2
            monitor._stop_event.clear()
            monitor._running = True

            monitor._thread = threading.Thread(target=monitor._poll_loop, daemon=True)
            monitor._thread.start()

            _wait_until(lambda: len(changes) > 0, timeout=1.0)
            monitor._stop_event.set()
            monitor._thread.join(timeout=1.0)

        assert len(changes) >= 1
        assert changes[0] == "devices_changed"


# =============================================================================
# CoreAudioDeviceMonitor
# =============================================================================


class TestCoreAudioDeviceMonitor:
    """Test CoreAudio device monitor."""

    @pytest.mark.macos
    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_install_and_remove_listener(self) -> None:
        monitor = CoreAudioDeviceMonitor(on_device_change=lambda _reason: None)
        monitor.start()
        assert monitor.running
        assert monitor._listeners_installed
        monitor.stop()
        assert not monitor._listeners_installed
        assert not monitor.running

    @pytest.mark.macos
    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_start_idempotent(self) -> None:
        monitor = CoreAudioDeviceMonitor(on_device_change=lambda _reason: None)
        monitor.start()
        monitor.start()  # Should not install twice
        assert monitor._listeners_installed
        monitor.stop()

    @pytest.mark.macos
    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_stop_idempotent(self) -> None:
        monitor = CoreAudioDeviceMonitor(on_device_change=lambda _reason: None)
        monitor.stop()  # Not started, should not raise

    @pytest.mark.macos
    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_callback_refs_kept(self) -> None:
        """Ctypes callback references must not be garbage collected."""
        monitor = CoreAudioDeviceMonitor(on_device_change=lambda _reason: None)
        monitor.start()
        assert len(monitor._callback_refs) == 3  # dIn, dOut, dev#
        monitor.stop()


# =============================================================================
# AudioCapture.emergency_abort()
# =============================================================================


class TestEmergencyAbort:
    """Test AudioCapture.emergency_abort() method."""

    def test_sets_needs_reconnect(self) -> None:
        capture = AudioCapture()
        assert capture.reconnect_reason is None
        capture.emergency_abort()
        assert capture.reconnect_reason == "callback_error"

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

    def test_on_device_change_default_input(self) -> None:
        """Default input change triggers reset when config is default."""
        from dictare.core.audio_manager import AudioManager

        config = MagicMock()
        config.input_device = ""  # Using default
        config.output_device = ""
        config.advanced.sample_rate = 16000
        config.advanced.channels = 1
        config.advanced.device = None

        manager = AudioManager(config=config)
        mock_audio = MagicMock(spec=AudioCapture)
        manager._audio = mock_audio

        # Track if _on_devices_updated is called
        updated = []
        manager._on_devices_updated = lambda: updated.append(1)

        with patch.object(manager, "reset_audio_input"):
            manager._on_device_change("default_input_changed")
            manager.reset_audio_input.assert_called_once()

        assert len(updated) == 1

    def test_on_device_change_fixed_input_ignored(self) -> None:
        """Default input change is ignored when a fixed device is configured."""
        from dictare.core.audio_manager import AudioManager

        config = MagicMock()
        config.input_device = "My USB Mic"
        config.output_device = ""

        manager = AudioManager(config=config)
        manager._audio = MagicMock(spec=AudioCapture)

        with patch.object(manager, "reset_audio_input"):
            manager._on_device_change("default_input_changed")
            manager.reset_audio_input.assert_not_called()

    def test_on_device_change_safe_without_audio(self) -> None:
        """Device change when _audio is None should not raise."""
        from dictare.core.audio_manager import AudioManager

        config = MagicMock()
        config.input_device = ""
        config.output_device = ""
        manager = AudioManager(config=config)
        manager._audio = None
        manager._on_device_change("default_input_changed")  # Should not raise

    def test_close_stops_device_monitor(self) -> None:
        """AudioManager.close() stops the device monitor."""
        from dictare.core.audio_manager import AudioManager

        config = MagicMock()
        manager = AudioManager(config=config)
        mock_monitor = MagicMock(spec=DeviceMonitor)
        manager._device_monitor = mock_monitor

        manager.close()
        mock_monitor.stop.assert_called_once()
        assert manager._device_monitor is None
