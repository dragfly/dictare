"""Tests for signal-handler registration and the functions they invoke.

Real signals are never sent to the test process: handlers are looked up via
signal.getsignal() and invoked directly, and the entry points that the
serve-mode handlers delegate to (AppController.on_hotkey_tap /
request_shutdown) are called as plain functions.
"""

from __future__ import annotations

import importlib
import signal
from unittest.mock import MagicMock, patch

import pytest

from dictare.app.controller import AppController

# ---------------------------------------------------------------------------
# TTS worker: SIGUSR2 stop handler
# ---------------------------------------------------------------------------

class TestTTSWorkerStopSignal:
    """dictare.tts.worker installs a SIGUSR2 handler at import time."""

    def test_sigusr2_handler_registered_on_import(self) -> None:
        """Importing the worker module registers _handle_stop_signal."""
        import dictare.tts.worker as worker_mod

        old_handler = signal.getsignal(signal.SIGUSR2)
        try:
            worker_mod = importlib.reload(worker_mod)
            assert (
                signal.getsignal(signal.SIGUSR2)
                is worker_mod._handle_stop_signal
            )
        finally:
            signal.signal(signal.SIGUSR2, old_handler)

    def test_stop_handler_sets_flag_and_stops_audio(self) -> None:
        """Invoking the handler sets _stop_requested and kills audio playback."""
        import dictare.tts.worker as worker_mod

        old_flag = worker_mod._stop_requested
        try:
            worker_mod._stop_requested = False
            with patch("dictare.tts.base.stop_audio_native") as mock_stop:
                worker_mod._handle_stop_signal(signal.SIGUSR2, None)

            assert worker_mod._stop_requested is True
            mock_stop.assert_called_once_with()
        finally:
            worker_mod._stop_requested = old_flag

# ---------------------------------------------------------------------------
# AppController: targets of the serve-mode SIGTERM/SIGINT/SIGUSR1 handlers
# ---------------------------------------------------------------------------

@pytest.fixture
def controller() -> AppController:
    """AppController with a mock config and no engine (pre-start state)."""
    return AppController(config=MagicMock())

class TestRequestShutdown:
    """request_shutdown() — invoked by the SIGTERM/SIGINT handler in serve.py."""

    def test_saves_session_and_stops_engine(self, controller: AppController) -> None:
        """With an engine: session state saved, run loop told to exit."""
        engine = MagicMock()
        controller._engine = engine

        controller.request_shutdown()

        engine.save_session_before_shutdown.assert_called_once_with()
        assert engine.running is False
        assert controller.wait_for_shutdown(timeout=0) is True

    def test_without_engine_still_signals_shutdown(
        self, controller: AppController
    ) -> None:
        """Before the engine exists (during model load), no crash — event set."""
        assert controller._engine is None
        controller.request_shutdown()
        assert controller.wait_for_shutdown(timeout=0) is True

    def test_wait_for_shutdown_times_out_before_request(
        self, controller: AppController
    ) -> None:
        """wait_for_shutdown returns False until shutdown is requested."""
        assert controller.wait_for_shutdown(timeout=0) is False

class TestHotkeyEntryPoints:
    """on_hotkey_* — invoked by the SIGUSR1 handler / IPC server in serve.py.

    These are wired BEFORE controller.start(), so each must be a safe no-op
    when the engine does not exist yet (late-binding guard).
    """

    def test_tap_without_engine_is_noop(self, controller: AppController) -> None:
        """SIGUSR1 during model load must not crash the process."""
        controller.on_hotkey_tap()  # Must not raise

    def test_tap_feeds_key_down_then_key_up(self, controller: AppController) -> None:
        """A tap simulates a complete press through the TapDetector."""
        engine = MagicMock()
        controller._engine = engine

        controller.on_hotkey_tap()

        engine.tap_detector.on_key_down.assert_called_once_with()
        engine.tap_detector.on_key_up.assert_called_once_with()

    def test_key_down_and_up_without_engine_are_noop(
        self, controller: AppController
    ) -> None:
        """IPC key events before start() are ignored, not fatal."""
        controller.on_hotkey_key_down()
        controller.on_hotkey_key_up()
        controller.on_hotkey_other_key()
        controller.on_hotkey_combo()  # Must not raise

    def test_key_down_and_up_forward_to_tap_detector(
        self, controller: AppController
    ) -> None:
        """IPC key.down / key.up feed the raw events into TapDetector."""
        engine = MagicMock()
        controller._engine = engine

        controller.on_hotkey_key_down()
        engine.tap_detector.on_key_down.assert_called_once_with()

        controller.on_hotkey_key_up()
        engine.tap_detector.on_key_up.assert_called_once_with()

    def test_other_key_cancels_pending_tap(self, controller: AppController) -> None:
        """A combo key while the hotkey is held cancels tap detection."""
        engine = MagicMock()
        controller._engine = engine

        controller.on_hotkey_other_key()
        engine.tap_detector.on_other_key.assert_called_once_with()

    def test_combo_toggles_mode(self, controller: AppController) -> None:
        """The mode-switch combo toggles agent/keyboard mode."""
        engine = MagicMock()
        controller._engine = engine

        controller.on_hotkey_combo()
        engine.toggle_mode.assert_called_once_with()
