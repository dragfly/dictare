"""Extra tests for DictareEngine — protocol commands, status, mute, agents."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from dictare.config import TTSConfig
from dictare.core.engine import DictareEngine, SessionStats, _MutableStats
from dictare.core.fsm import AppState


class MockAgent:
    """Mock agent for testing."""

    def __init__(self, agent_id: str) -> None:
        self._id = agent_id
        self.messages: list = []

    @property
    def id(self) -> str:
        return self._id

    def send(self, message) -> bool:
        self.messages.append(message)
        return True


class MockConfig:
    """Mock config for testing."""

    def __init__(self) -> None:
        self.verbose = False

        self.stt = MagicMock()
        self.stt.hw_accel = False
        self.stt.model = "tiny"
        self.stt.advanced.device = "cpu"
        self.stt.advanced.compute_type = "int8"
        self.stt.language = "en"
        self.stt.advanced.hotwords = ""
        self.stt.advanced.beam_size = 5
        self.stt.advanced.max_repetitions = 3
        self.stt.translate = False

        self.audio = MagicMock()
        self.audio.silence_ms = 1200
        self.audio.advanced.sample_rate = 16000
        self.audio.max_duration = 30
        self.audio.audio_feedback = False
        self.audio.headphones_mode = True
        self.audio.input_device = ""
        self.audio.output_device = ""
        self.audio.sounds = {}

        self.output = MagicMock()
        self.output.mode = "agents"
        self.output.typing_delay_ms = 0
        self.output.auto_submit = True

        self.hotkey = MagicMock()
        self.hotkey.key = "F18"
        self.hotkey.device = None

        self.keyboard = MagicMock()
        self.keyboard.shortcuts = {}

        self.stats = MagicMock()
        self.stats.typing_wpm = 40

        self.tts = TTSConfig(engine="espeak", language="en", speed=175, voice="")

        self.pipeline = MagicMock()
        self.pipeline.enabled = False
        self.pipeline.mute_filter.mute_phrases = []
        self.pipeline.mute_filter.listen_phrases = []


def _wait_for_controller(engine, *, predicate=None, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if engine._controller._queue.empty() and (predicate is None or predicate()):
            return
        time.sleep(0.001)
    time.sleep(0.005)


# ---------------------------------------------------------------------------
# SessionStats / _MutableStats
# ---------------------------------------------------------------------------

class TestSessionStats:
    """Test SessionStats and _MutableStats."""

    def test_mutable_stats_snapshot(self) -> None:
        ms = _MutableStats(chars=100, words=20, count=5)
        snap = ms.snapshot()
        assert isinstance(snap, SessionStats)
        assert snap.chars == 100
        assert snap.words == 20
        assert snap.count == 5

    def test_session_stats_is_frozen(self) -> None:
        ss = SessionStats(chars=10)
        with pytest.raises(AttributeError):
            ss.chars = 20  # type: ignore[misc]

    def test_snapshot_defaults(self) -> None:
        ms = _MutableStats()
        snap = ms.snapshot()
        assert snap.chars == 0
        assert snap.audio_seconds == 0.0
        assert snap.start_time is None


# ---------------------------------------------------------------------------
# Protocol commands
# ---------------------------------------------------------------------------

class TestHandleProtocolCommand:
    """Test handle_protocol_command."""

    def test_stt_start(self) -> None:
        engine = DictareEngine(config=MockConfig())
        result = engine.handle_protocol_command({"command": "stt.start"})
        assert result["status"] == "ok"
        assert result["listening"] is True

    def test_stt_stop(self) -> None:
        engine = DictareEngine(config=MockConfig())
        result = engine.handle_protocol_command({"command": "stt.stop"})
        assert result["status"] == "ok"
        assert result["listening"] is False

    def test_stt_toggle(self) -> None:
        engine = DictareEngine(config=MockConfig())
        result = engine.handle_protocol_command({"command": "stt.toggle"})
        assert result["status"] == "ok"

    def test_ping(self) -> None:
        engine = DictareEngine(config=MockConfig())
        result = engine.handle_protocol_command({"command": "ping"})
        assert result["pong"] is True

    def test_engine_shutdown(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._exit_watchdog_cancel.set()  # prevent os._exit
        with patch("dictare.utils.state.save_state"):
            result = engine.handle_protocol_command({"command": "engine.shutdown"})
        assert result["status"] == "ok"
        assert engine._running is False

    def test_engine_restart(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._exit_watchdog_cancel.set()
        with patch("dictare.utils.state.save_state"):
            result = engine.handle_protocol_command({"command": "engine.restart"})
        assert result["status"] == "ok"
        assert engine._running is False

    def test_unknown_command(self) -> None:
        engine = DictareEngine(config=MockConfig())
        result = engine.handle_protocol_command({"command": "nonexistent"})
        assert result["status"] == "error"
        assert "Unknown" in result["error"]

    def test_hotkey_capture_no_listener(self) -> None:
        engine = DictareEngine(config=MockConfig())
        result = engine.handle_protocol_command({"command": "hotkey.capture"})
        assert result["key"] is None


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    """Test get_status method."""

    def test_status_contains_openvip_field(self) -> None:
        engine = DictareEngine(config=MockConfig())
        status = engine.get_status()
        assert status["openvip"] == "1.0"

    def test_status_contains_platform(self) -> None:
        engine = DictareEngine(config=MockConfig())
        status = engine.get_status()
        assert "platform" in status
        assert status["platform"]["name"] == "Dictare"

    def test_status_state_off(self) -> None:
        engine = DictareEngine(config=MockConfig())
        status = engine.get_status()
        assert status["platform"]["state"] == "off"

    def test_status_state_listening(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._state_manager.transition(AppState.LISTENING)
        status = engine.get_status()
        assert status["platform"]["state"] == "listening"

    def test_status_muted_overrides_listening(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._state_manager.transition(AppState.LISTENING)
        engine._voice_muted = True
        status = engine.get_status()
        assert status["platform"]["state"] == "muted"

    def test_status_shows_output_mode(self) -> None:
        config = MockConfig()
        config.output.mode = "keyboard"
        engine = DictareEngine(config=config)
        status = engine.get_status()
        assert status["platform"]["mode"] == "keyboard"

    def test_status_connected_agents(self) -> None:
        engine = DictareEngine(config=MockConfig())
        agent = MockAgent("claude")
        engine.register_agent(agent)
        status = engine.get_status()
        assert "claude" in status["connected_agents"]

    def test_status_stt_info(self) -> None:
        engine = DictareEngine(config=MockConfig())
        status = engine.get_status()
        assert status["platform"]["stt"]["model_name"] == "tiny"

    def test_status_stats(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._stats.count = 5
        engine._stats.words = 50
        status = engine.get_status()
        stats = status["platform"]["stats"]
        assert stats["transcriptions"] >= 5
        assert stats["words"] >= 50


# ---------------------------------------------------------------------------
# Mute / Unmute
# ---------------------------------------------------------------------------

class TestMuteUnmute:
    """Test voice mute functionality."""

    def test_mute_sets_flag(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._running = True
        with patch("dictare.utils.state.save_state"):
            engine.mute()
        assert engine._voice_muted is True

    def test_mute_idempotent(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._running = True
        with patch("dictare.utils.state.save_state"):
            engine.mute()
            engine.mute()  # second call should be no-op
        assert engine._voice_muted is True

    def test_unmute_clears_flag(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._running = True
        engine._voice_muted = True
        with patch("dictare.utils.state.save_state"):
            engine.unmute()
        assert engine._voice_muted is False

    def test_unmute_idempotent(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._running = True
        with patch("dictare.utils.state.save_state"):
            engine.unmute()  # already unmuted
        assert engine._voice_muted is False


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------

class TestAgentRegistration:
    """Test agent register/unregister."""

    def test_register_adds_agent(self) -> None:
        engine = DictareEngine(config=MockConfig())
        agent = MockAgent("test")
        result = engine.register_agent(agent)
        assert result is True
        assert "test" in engine.agents

    def test_unregister_removes_agent(self) -> None:
        engine = DictareEngine(config=MockConfig())
        agent = MockAgent("test")
        engine.register_agent(agent)
        engine.unregister_agent("test")
        assert "test" not in engine.agents

    def test_visible_agents_hides_internal(self) -> None:
        engine = DictareEngine(config=MockConfig())
        agent = MockAgent("claude")
        internal = MockAgent("__keyboard__")
        engine.register_agent(agent)
        engine.register_agent(internal)
        assert "claude" in engine.visible_agents
        assert "__keyboard__" not in engine.visible_agents


# ---------------------------------------------------------------------------
# Output mode toggle
# ---------------------------------------------------------------------------

class TestOutputMode:
    """Test output mode switching."""

    def test_toggle_mode(self) -> None:
        config = MockConfig()
        config.output.mode = "agents"
        engine = DictareEngine(config=config)
        assert engine.agent_mode is True
        engine.toggle_mode()
        assert engine.agent_mode is False

    def test_toggle_mode_back(self) -> None:
        config = MockConfig()
        config.output.mode = "keyboard"
        engine = DictareEngine(config=config)
        assert engine.agent_mode is False
        engine.toggle_mode()
        assert engine.agent_mode is True

    def test_set_output_mode(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine.set_output_mode("keyboard")
        assert engine.agent_mode is False
        engine.set_output_mode("agents")
        assert engine.agent_mode is True


# ---------------------------------------------------------------------------
# Agent focus
# ---------------------------------------------------------------------------

class TestAgentFocus:
    """Test set_agent_focus."""

    def test_set_focus(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._running = True
        with patch("dictare.utils.state.save_state"):
            engine.set_agent_focus("claude", True)
        assert engine._feedback_policy.focused_agent == "claude"

    def test_set_focus_false_clears(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._running = True
        with patch("dictare.utils.state.save_state"):
            engine.set_agent_focus("claude", True)
            # Focus-out is debounced, so set it directly
            engine._feedback_policy._focus["claude"] = False
        assert engine._feedback_policy.focused_agent is None


# ---------------------------------------------------------------------------
# Resend last
# ---------------------------------------------------------------------------

class TestResendLast:
    """Test resend_last."""

    def test_no_text_returns_false(self) -> None:
        engine = DictareEngine(config=MockConfig())
        assert engine.resend_last() is False

    def test_with_text_returns_true(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._last_text = "hello"
        agent = MockAgent("test")
        engine.register_agent(agent)
        # Set current agent
        engine._agent_mgr.switch_by_name("test")
        result = engine.resend_last()
        assert result is True


# ---------------------------------------------------------------------------
# Discard current
# ---------------------------------------------------------------------------

class TestDiscardCurrent:
    """Test discard_current_internal."""

    def test_discard_with_audio_manager(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._audio_manager = MagicMock()
        engine._discard_current_internal()
        engine._audio_manager.clear_queue.assert_called_once()
        engine._audio_manager.reset_vad.assert_called_once()

    def test_discard_without_audio_manager(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._audio_manager = None
        engine._discard_current_internal()  # should not raise


# ---------------------------------------------------------------------------
# Stop engine
# ---------------------------------------------------------------------------

class TestEngineStop:
    """Test engine stop."""

    def test_stop_sets_running_false(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._running = True
        engine.stop()
        assert engine._running is False

    def test_stop_closes_audio_manager(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._audio_manager = MagicMock()
        engine.stop()
        engine._audio_manager.close.assert_called_once()

    def test_stop_without_audio_manager(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine.stop()  # should not raise


# ---------------------------------------------------------------------------
# Exit watchdog
# ---------------------------------------------------------------------------

class TestExitWatchdog:
    """Test _start_exit_watchdog."""

    def test_watchdog_respects_cancel(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._exit_watchdog_cancel.set()
        # This should not call os._exit because cancel is set
        engine._start_exit_watchdog(exit_code=1, timeout=0.01)
        import time as _time
        _time.sleep(0.05)  # wait for watchdog to check cancel
        # If we're still here, the cancel worked


# ---------------------------------------------------------------------------
# _get_session_stats
# ---------------------------------------------------------------------------

class TestGetSessionStats:
    """Test _get_session_stats."""

    def test_includes_baseline(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._today_baseline = {"transcriptions": 10, "words": 100}
        engine._stats.count = 5
        engine._stats.words = 50
        stats = engine._get_session_stats()
        assert stats["transcriptions"] == 15
        assert stats["words"] == 150

    def test_phrase_non_empty_when_count_positive(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._stats.count = 1
        stats = engine._get_session_stats()
        assert stats["phrase"] != ""

    def test_phrase_empty_when_count_zero(self) -> None:
        engine = DictareEngine(config=MockConfig())
        stats = engine._get_session_stats()
        assert stats["phrase"] == ""


# ---------------------------------------------------------------------------
# Submit action
# ---------------------------------------------------------------------------

class TestSubmitAction:
    """Test _submit_action."""

    def test_defer_during_recording(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._state_manager.transition(AppState.RECORDING, force=True)
        engine._submit_action()
        assert engine._submit_pending is True

    def test_defer_during_transcribing(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._state_manager.transition(AppState.TRANSCRIBING, force=True)
        engine._submit_action()
        assert engine._submit_pending is True

    def test_no_agent_noop(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._state_manager.transition(AppState.LISTENING)
        # No agents registered
        engine._submit_action()
        assert engine._submit_pending is False

    def test_sends_submit_to_agent(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._state_manager.transition(AppState.LISTENING)
        agent = MockAgent("test")
        engine.register_agent(agent)
        engine._agent_mgr.switch_by_name("test")
        engine._submit_action()
        assert len(agent.messages) == 1
        assert "submit" in agent.messages[0].get("x_input", {}).get("ops", [])


# ---------------------------------------------------------------------------
# Process queued audio
# ---------------------------------------------------------------------------

class TestProcessQueuedAudio:
    """Test _process_queued_audio."""

    def test_no_audio_manager(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._audio_manager = None
        engine._process_queued_audio()  # should not raise

    def test_empty_queue(self) -> None:
        engine = DictareEngine(config=MockConfig())
        engine._audio_manager = MagicMock()
        engine._audio_manager.has_queued_audio = False
        engine._process_queued_audio()  # should not raise
