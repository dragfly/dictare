"""Extra tests for AppController — lifecycle, app commands, properties."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dictare.app.controller import AppController, _ControllerEvents

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> MagicMock:
    """Build a minimal MockConfig for AppController."""
    config = MagicMock()
    config.verbose = False
    config.server.host = "127.0.0.1"
    config.server.port = 0
    config.output.mode = "agents"
    config.audio.audio_feedback = False
    config.audio.headphones_mode = True
    config.audio.sounds = {}
    config.stats.typing_wpm = 40
    return config


def _make_engine() -> MagicMock:
    """Build a mock engine for testing controller methods."""
    engine = MagicMock()
    engine.is_listening = True
    engine.state = MagicMock()
    engine.agent_mode = True
    engine.current_agent = "claude"
    engine.agents = ["claude", "cursor"]
    engine.stats = MagicMock()
    engine.stats.count = 5
    engine.stats.chars = 200
    engine.stats.words = 40
    engine.stats.audio_seconds = 10.0
    engine.stats.transcription_seconds = 2.0
    engine.stats.injection_seconds = 0.5
    engine._tap_detector = MagicMock()
    return engine


# ---------------------------------------------------------------------------
# AppController initialization
# ---------------------------------------------------------------------------

class TestAppControllerInit:
    """Test AppController basic initialization."""

    def test_initially_not_running(self) -> None:
        config = _make_config()
        ctrl = AppController(config)
        assert ctrl.is_running is False

    def test_engine_is_none(self) -> None:
        config = _make_config()
        ctrl = AppController(config)
        assert ctrl.engine is None

    def test_config_stored(self) -> None:
        config = _make_config()
        ctrl = AppController(config)
        assert ctrl.config is config


# ---------------------------------------------------------------------------
# Properties without engine
# ---------------------------------------------------------------------------

class TestPropertiesWithoutEngine:
    """Test properties when engine is not started."""

    def test_is_listening_false(self) -> None:
        ctrl = AppController(_make_config())
        assert ctrl.is_listening is False

    def test_current_agent_none(self) -> None:
        ctrl = AppController(_make_config())
        assert ctrl.current_agent is None

    def test_agents_empty(self) -> None:
        ctrl = AppController(_make_config())
        assert ctrl.agents == []


# ---------------------------------------------------------------------------
# Properties with engine
# ---------------------------------------------------------------------------

class TestPropertiesWithEngine:
    """Test properties when engine is set."""

    def test_is_listening_delegates(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        assert ctrl.is_listening is True

    def test_current_agent_delegates(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        assert ctrl.current_agent == "claude"

    def test_agents_delegates(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        assert ctrl.agents == ["claude", "cursor"]


# ---------------------------------------------------------------------------
# App commands without engine — no-op
# ---------------------------------------------------------------------------

class TestAppCommandsWithoutEngine:
    """All app commands are no-ops when engine is None."""

    def test_toggle_listening_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.toggle_listening()  # should not raise

    def test_next_agent_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.next_agent()

    def test_prev_agent_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.prev_agent()

    def test_switch_to_agent_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.switch_to_agent("claude")

    def test_switch_to_agent_index_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.switch_to_agent_index(1)

    def test_repeat_last_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.repeat_last()

    def test_set_output_mode_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.set_output_mode("keyboard")

    def test_on_hotkey_tap_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.on_hotkey_tap()

    def test_on_hotkey_key_down_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.on_hotkey_key_down()

    def test_on_hotkey_key_up_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.on_hotkey_key_up()

    def test_on_hotkey_other_key_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.on_hotkey_other_key()

    def test_on_hotkey_combo_noop(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.on_hotkey_combo()


# ---------------------------------------------------------------------------
# App commands with engine
# ---------------------------------------------------------------------------

class TestAppCommandsWithEngine:
    """Test that app commands delegate to engine."""

    def test_toggle_listening(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl.toggle_listening()
        ctrl._engine.set_listening.assert_called_once_with(False)

    def test_next_agent(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl.next_agent()
        ctrl._engine.switch_agent.assert_called_once_with(1)

    def test_prev_agent(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl.prev_agent()
        ctrl._engine.switch_agent.assert_called_once_with(-1)

    def test_switch_to_agent(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl.switch_to_agent("cursor")
        ctrl._engine.switch_to_agent_by_name.assert_called_once_with("cursor")

    def test_switch_to_agent_forces_agents_mode(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl._engine.agent_mode = False  # keyboard mode
        ctrl.switch_to_agent("cursor")
        ctrl._engine.set_output_mode.assert_called_once_with("agents")

    def test_switch_to_agent_index(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl.switch_to_agent_index(2)
        ctrl._engine.switch_to_agent_by_index.assert_called_once_with(2)

    def test_repeat_last(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl.repeat_last()
        ctrl._engine.resend_last.assert_called_once()

    def test_set_output_mode(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl.set_output_mode("keyboard")
        ctrl._engine.set_output_mode.assert_called_once_with("keyboard")

    def test_on_hotkey_tap(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl.on_hotkey_tap()
        ctrl._engine._tap_detector.on_key_down.assert_called_once()
        ctrl._engine._tap_detector.on_key_up.assert_called_once()

    def test_on_hotkey_combo(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl.on_hotkey_combo()
        ctrl._engine.toggle_mode.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_app_command
# ---------------------------------------------------------------------------

class TestHandleAppCommand:
    """Test _handle_app_command routing."""

    def test_output_set_agent(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        result = ctrl._handle_app_command({"command": "output.set_agent:cursor"})
        assert result["status"] == "ok"
        ctrl._engine.switch_to_agent_by_name.assert_called_once_with("cursor")

    def test_output_set_mode(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        result = ctrl._handle_app_command({"command": "output.set_mode:keyboard"})
        assert result["status"] == "ok"
        assert result["mode"] == "keyboard"
        ctrl._engine.set_output_mode.assert_called_once_with("keyboard")

    def test_unknown_command(self) -> None:
        ctrl = AppController(_make_config())
        result = ctrl._handle_app_command({"command": "foo.bar"})
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

class TestShutdown:
    """Test request_shutdown and wait_for_shutdown."""

    def test_request_shutdown_sets_event(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._engine = _make_engine()
        ctrl.request_shutdown()
        assert ctrl._shutdown_event.is_set()
        ctrl._engine.save_session_before_shutdown.assert_called_once()

    def test_wait_for_shutdown_returns_immediately_when_set(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._shutdown_event.set()
        assert ctrl.wait_for_shutdown(timeout=0.01) is True

    def test_wait_for_shutdown_returns_false_on_timeout(self) -> None:
        ctrl = AppController(_make_config())
        assert ctrl.wait_for_shutdown(timeout=0.01) is False


# ---------------------------------------------------------------------------
# Stop (no real engine)
# ---------------------------------------------------------------------------

class TestControllerStop:
    """Test stop() with mocked components."""

    def test_stop_when_not_running(self) -> None:
        ctrl = AppController(_make_config())
        ctrl.stop()  # should not raise

    def test_stop_cleans_up(self) -> None:
        ctrl = AppController(_make_config())
        ctrl._running = True

        engine = _make_engine()
        engine.stats = MagicMock()
        engine.stats.count = 0
        ctrl._engine = engine

        http_server = MagicMock()
        ctrl._http_server = http_server

        bindings = MagicMock()
        ctrl._bindings = bindings

        logger_mock = MagicMock()
        ctrl._logger = logger_mock

        ctrl.stop()

        assert ctrl._running is False
        http_server.stop.assert_called_once()
        engine.stop.assert_called_once()
        bindings.stop.assert_called_once()
        logger_mock.close.assert_called_once()


# ---------------------------------------------------------------------------
# Single instance (PID file)
# ---------------------------------------------------------------------------

class TestSingleInstance:
    """Test _check_single_instance and _cleanup_pid."""

    def test_check_single_instance_writes_pid(self, tmp_path) -> None:
        import os

        ctrl = AppController(_make_config())
        pid_path = tmp_path / "engine.pid"
        dictare_dir = tmp_path

        with (
            patch("dictare.utils.paths.get_pid_path", return_value=pid_path),
            patch("dictare.utils.paths.get_dictare_dir", return_value=dictare_dir),
        ):
            ctrl._check_single_instance()

        assert pid_path.exists()
        assert pid_path.read_text().strip() == str(os.getpid())

    def test_check_single_instance_stale_pid(self, tmp_path) -> None:
        """Stale PID file (process gone) is overwritten."""
        import os

        ctrl = AppController(_make_config())
        pid_path = tmp_path / "engine.pid"
        dictare_dir = tmp_path

        # Write a stale PID (use PID 99999999 which almost certainly doesn't exist)
        pid_path.write_text("99999999")

        with (
            patch("dictare.utils.paths.get_pid_path", return_value=pid_path),
            patch("dictare.utils.paths.get_dictare_dir", return_value=dictare_dir),
        ):
            ctrl._check_single_instance()

        assert pid_path.read_text().strip() == str(os.getpid())

    def test_check_single_instance_live_pid_raises(self, tmp_path) -> None:
        """Live PID file raises RuntimeError."""
        import os

        ctrl = AppController(_make_config())
        pid_path = tmp_path / "engine.pid"
        dictare_dir = tmp_path

        # Write our own PID (which is definitely running)
        pid_path.write_text(str(os.getpid()))

        with (
            patch("dictare.utils.paths.get_pid_path", return_value=pid_path),
            patch("dictare.utils.paths.get_dictare_dir", return_value=dictare_dir),
        ):
            with pytest.raises(RuntimeError, match="already running"):
                ctrl._check_single_instance()

    def test_cleanup_pid(self, tmp_path) -> None:
        """_cleanup_pid removes PID file only if it contains our PID."""
        import os

        ctrl = AppController(_make_config())
        pid_path = tmp_path / "engine.pid"
        pid_path.write_text(str(os.getpid()))

        with patch("dictare.utils.paths.get_pid_path", return_value=pid_path):
            ctrl._cleanup_pid()

        assert not pid_path.exists()

    def test_cleanup_pid_wrong_pid(self, tmp_path) -> None:
        """_cleanup_pid does NOT remove PID file with a different PID."""
        ctrl = AppController(_make_config())
        pid_path = tmp_path / "engine.pid"
        pid_path.write_text("99999")

        with patch("dictare.utils.paths.get_pid_path", return_value=pid_path):
            ctrl._cleanup_pid()

        assert pid_path.exists()


# ---------------------------------------------------------------------------
# _ControllerEvents
# ---------------------------------------------------------------------------

class TestControllerEvents:
    """Test _ControllerEvents callbacks."""

    def test_on_agent_change_logs(self) -> None:
        config = _make_config()
        config.audio.audio_feedback = False
        events = _ControllerEvents(config)
        # Should not raise even without engine
        events.on_agent_change("claude", 0)

    def test_on_state_change_off_to_listening(self) -> None:
        from dictare.core.fsm import AppState

        config = _make_config()
        config.audio.audio_feedback = False
        events = _ControllerEvents(config)
        # With audio_feedback disabled, sounds are skipped
        events.on_state_change(AppState.OFF, AppState.LISTENING, "hotkey")

    def test_on_state_change_listening_to_off(self) -> None:
        from dictare.core.fsm import AppState

        config = _make_config()
        config.audio.audio_feedback = False
        events = _ControllerEvents(config)
        events.on_state_change(AppState.LISTENING, AppState.OFF, "hotkey")
