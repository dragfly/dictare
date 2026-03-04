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
    """Test AudioManager device monitor integration.

    _on_device_change() always reinits PortAudio and restarts the input stream.
    Tests verify the policy decisions (reset output, notify removed, etc.)
    while mocking the low-level PA/stream methods.
    """

    def _make_manager(self, *, input_device: str = "", output_device: str = ""):
        """Create an AudioManager with mocked internals for policy testing."""
        from dictare.core.audio_manager import AudioManager

        config = MagicMock()
        config.input_device = input_device
        config.output_device = output_device
        config.advanced.sample_rate = 16000
        config.advanced.channels = 1
        config.advanced.device = None

        manager = AudioManager(config=config)
        manager._audio = MagicMock(spec=AudioCapture)

        # Patch low-level methods that interact with PortAudio
        patcher_reinit = patch.object(manager, "_reinit_portaudio")
        patcher_restart = patch.object(manager, "_restart_input_stream")
        mock_reinit = patcher_reinit.start()
        mock_restart = patcher_restart.start()

        def cleanup():
            patcher_reinit.stop()
            patcher_restart.stop()

        return manager, mock_reinit, mock_restart, cleanup

    def test_on_device_change_default_input(self) -> None:
        """Default input change reinits PA and restarts stream."""
        manager, mock_reinit, mock_restart, cleanup = self._make_manager()
        try:
            updated = []
            manager._on_devices_updated = lambda: updated.append(1)
            manager._on_device_change("default_input_changed")
            mock_reinit.assert_called_once()
            mock_restart.assert_called_once()
            assert len(updated) == 1
        finally:
            cleanup()

    def test_on_device_change_fixed_input_ignored(self) -> None:
        """Default input change with fixed device: reinit + restart but no output reset."""
        manager, mock_reinit, mock_restart, cleanup = self._make_manager(input_device="My USB Mic")
        try:
            with patch.object(manager, "reset_audio_output") as mock_output:
                manager._on_device_change("default_input_changed")
                mock_output.assert_not_called()
            mock_reinit.assert_called_once()
            mock_restart.assert_called_once()
        finally:
            cleanup()

    def test_on_device_change_default_output_resets(self) -> None:
        """Default output change triggers reset_audio_output when config is default."""
        manager, _, _, cleanup = self._make_manager()
        try:
            with patch.object(manager, "reset_audio_output") as mock_reset:
                manager._on_device_change("default_output_changed")
                mock_reset.assert_called_once_with("")
        finally:
            cleanup()

    def test_on_device_change_fixed_output_ignored(self) -> None:
        """Default output change is ignored when a fixed output device is configured."""
        manager, _, _, cleanup = self._make_manager(output_device="My Speakers")
        try:
            with patch.object(manager, "reset_audio_output") as mock_reset:
                manager._on_device_change("default_output_changed")
                mock_reset.assert_not_called()
        finally:
            cleanup()

    def test_devices_changed_fixed_input_gone_fallback(self) -> None:
        """When fixed input device disappears, notify config removal."""
        manager, _, _, cleanup = self._make_manager(input_device="My USB Mic")
        try:
            removed_calls: list[str] = []
            manager._on_fixed_device_removed = lambda key: removed_calls.append(key)

            with (
                patch.object(AudioCapture, "list_devices", return_value=[
                    {"name": "Built-in Microphone", "index": 0, "channels": 1, "sample_rate": 44100},
                ]),
                patch.object(AudioCapture, "list_output_devices", return_value=[
                    {"name": "Built-in Output", "index": 1, "channels": 2, "sample_rate": 44100},
                ]),
            ):
                manager._on_device_change("devices_changed")

            assert removed_calls == ["audio.input_device"]
        finally:
            cleanup()

    def test_devices_changed_fixed_output_gone_fallback(self) -> None:
        """When fixed output device disappears, fallback to default and clear config."""
        manager, _, _, cleanup = self._make_manager(output_device="My Headphones")
        try:
            removed_calls: list[str] = []
            manager._on_fixed_device_removed = lambda key: removed_calls.append(key)

            with (
                patch.object(AudioCapture, "list_devices", return_value=[
                    {"name": "Built-in Microphone", "index": 0, "channels": 1, "sample_rate": 44100},
                ]),
                patch.object(AudioCapture, "list_output_devices", return_value=[
                    {"name": "Built-in Output", "index": 1, "channels": 2, "sample_rate": 44100},
                ]),
                patch.object(manager, "reset_audio_output") as mock_reset,
            ):
                manager._on_device_change("devices_changed")
                mock_reset.assert_called_once_with("")

            assert removed_calls == ["audio.output_device"]
        finally:
            cleanup()

    def test_devices_changed_fixed_devices_still_present(self) -> None:
        """When device list changes but our fixed devices are still present, no output reset."""
        manager, _, _, cleanup = self._make_manager(
            input_device="My USB Mic", output_device="My Headphones",
        )
        try:
            with (
                patch.object(AudioCapture, "list_devices", return_value=[
                    {"name": "Built-in Microphone", "index": 0, "channels": 1, "sample_rate": 44100},
                    {"name": "My USB Mic", "index": 2, "channels": 1, "sample_rate": 48000},
                ]),
                patch.object(AudioCapture, "list_output_devices", return_value=[
                    {"name": "Built-in Output", "index": 1, "channels": 2, "sample_rate": 44100},
                    {"name": "My Headphones", "index": 3, "channels": 2, "sample_rate": 48000},
                ]),
                patch.object(manager, "reset_audio_output") as mock_output,
            ):
                manager._on_device_change("devices_changed")
                mock_output.assert_not_called()
        finally:
            cleanup()

    def test_all_reasons_call_on_devices_updated(self) -> None:
        """Every device change reason triggers _on_devices_updated callback."""
        manager, _, _, cleanup = self._make_manager(
            input_device="Fixed", output_device="Fixed",
        )
        try:
            updated: list[str] = []
            manager._on_devices_updated = lambda: updated.append("called")

            with (
                patch.object(AudioCapture, "list_devices", return_value=[
                    {"name": "Fixed", "index": 0, "channels": 1, "sample_rate": 44100},
                ]),
                patch.object(AudioCapture, "list_output_devices", return_value=[
                    {"name": "Fixed", "index": 1, "channels": 2, "sample_rate": 44100},
                ]),
            ):
                for reason in ("default_input_changed", "default_output_changed", "devices_changed"):
                    manager._on_device_change(reason)

            assert len(updated) == 3
        finally:
            cleanup()

    def test_all_reasons_always_restart_input(self) -> None:
        """Every device change reinits PA and restarts input stream."""
        manager, mock_reinit, mock_restart, cleanup = self._make_manager(
            input_device="Fixed", output_device="Fixed",
        )
        try:
            with (
                patch.object(AudioCapture, "list_devices", return_value=[
                    {"name": "Fixed", "index": 0, "channels": 1, "sample_rate": 44100},
                ]),
                patch.object(AudioCapture, "list_output_devices", return_value=[
                    {"name": "Fixed", "index": 1, "channels": 2, "sample_rate": 44100},
                ]),
            ):
                for reason in ("default_input_changed", "default_output_changed", "devices_changed"):
                    manager._on_device_change(reason)

            assert mock_reinit.call_count == 3
            assert mock_restart.call_count == 3
        finally:
            cleanup()

    def test_on_device_change_safe_without_audio(self) -> None:
        """Device change when _audio is None should not raise."""
        manager, _, _, cleanup = self._make_manager()
        try:
            manager._audio = None
            manager._on_device_change("default_input_changed")  # Should not raise
        finally:
            cleanup()

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
