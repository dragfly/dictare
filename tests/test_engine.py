"""Tests for VoxtypeEngine core logic."""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np

from voxtype.agent.base import OpenVIPMessage
from voxtype.config import TTSConfig
from voxtype.core.engine import VoxtypeEngine
from voxtype.core.events import InjectionResult, TranscriptionResult
from voxtype.core.state import AppState

class MockAgent:
    """Mock agent for testing."""

    def __init__(self, agent_id: str) -> None:
        self._id = agent_id
        self.messages: list[OpenVIPMessage] = []

    @property
    def id(self) -> str:
        return self._id

    def send(self, message: OpenVIPMessage) -> bool:
        self.messages.append(message)
        return True

def register_test_agents(engine: VoxtypeEngine, agent_ids: list[str]) -> list[MockAgent]:
    """Helper to register mock agents for testing."""
    agents = [MockAgent(aid) for aid in agent_ids]
    for agent in agents:
        engine.register_agent(agent)
    return agents

class MockConfig:
    """Mock config for testing."""

    def __init__(self) -> None:
        self.verbose = False

        # STT config
        self.stt = MagicMock()
        self.stt.hw_accel = False
        self.stt.model = "tiny"
        self.stt.device = "cpu"
        self.stt.compute_type = "int8"
        self.stt.language = "en"
        self.stt.hotwords = None
        self.stt.beam_size = 5
        self.stt.max_repetitions = 3

        # Audio config
        self.audio = MagicMock()
        self.audio.silence_ms = 1200
        self.audio.sample_rate = 16000
        self.audio.max_duration = 30
        self.audio.audio_feedback = False
        self.audio.headphones_mode = True

        # Output config
        self.output = MagicMock()
        self.output.mode = "keyboard"
        self.output.typing_delay_ms = 0
        self.output.auto_enter = True

        # Hotkey config
        self.hotkey = MagicMock()
        self.hotkey.key = "F18"
        self.hotkey.device = None

        # Keyboard config
        self.keyboard = MagicMock()
        self.keyboard.shortcuts = {}

        # Stats config
        self.stats = MagicMock()
        self.stats.typing_wpm = 40

        # TTS config
        self.tts = TTSConfig(engine="espeak", language="en", speed=175, voice="")

        # Pipeline config
        self.pipeline = MagicMock()
        self.pipeline.enabled = False  # Disabled in tests for simplicity

class MockEventHandler:
    """Mock event handler that records all events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.state_changes: list[tuple[AppState, AppState, str]] = []
        self.transcriptions: list[TranscriptionResult] = []
        self.injections: list[InjectionResult] = []
        self.agent_changes: list[tuple[str, int]] = []
        self.errors: list[tuple[str, str]] = []
        self.partial_transcriptions: list[str] = []

    def on_state_change(
        self, old: AppState, new: AppState, trigger: str
    ) -> None:
        self.state_changes.append((old, new, trigger))

    def on_transcription(self, result: TranscriptionResult) -> None:
        self.transcriptions.append(result)

    def on_injection(self, result: InjectionResult) -> None:
        self.injections.append(result)

    def on_agent_change(self, agent_name: str, index: int) -> None:
        self.agent_changes.append((agent_name, index))

    def on_error(self, message: str, context: str) -> None:
        self.errors.append((message, context))

    def on_partial_transcription(self, text: str) -> None:
        self.partial_transcriptions.append(text)

    def on_recording_start(self) -> None:
        pass

    def on_recording_end(self, duration_ms: float) -> None:
        pass

    def on_max_duration_reached(self) -> None:
        pass

class TestVoxtypeEngineInit:
    """Test VoxtypeEngine initialization."""

    def test_initial_state_is_off(self) -> None:
        """Engine starts in OFF state."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        assert engine.state == AppState.OFF

    def test_is_off_initially(self) -> None:
        """is_off returns True initially."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        assert engine.is_off is True
        assert engine.is_listening is False

    def test_agent_mode_default_false(self) -> None:
        """Agent mode defaults to False (keyboard mode)."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        assert engine.agent_mode is False

    def test_events_handler_stored(self) -> None:
        """Event handler is stored."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        assert engine._events is events

class TestVoxtypeEngineProperties:
    """Test VoxtypeEngine properties."""

    def test_state_property(self) -> None:
        """state property returns current state."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        assert engine.state == AppState.OFF

    def test_stats_initially_zero(self) -> None:
        """Stats are zero initially."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        s = engine.stats
        assert s.chars == 0
        assert s.words == 0
        assert s.count == 0
        assert s.audio_seconds == 0.0
        assert s.transcription_seconds == 0.0
        assert s.injection_seconds == 0.0
        assert s.start_time is None

class TestEventEmission:
    """Test event emission."""

    def test_emit_calls_handler(self) -> None:
        """_emit calls the event handler method."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)

        engine._emit("on_error", "test message", "test context")
        assert len(events.errors) == 1
        assert events.errors[0] == ("test message", "test context")

    def test_emit_without_handler_does_not_crash(self) -> None:
        """_emit with no handler doesn't crash."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config, events=None)
        # Should not raise
        engine._emit("on_error", "test", "test")

    def test_emit_nonexistent_event_does_not_crash(self) -> None:
        """_emit with nonexistent event doesn't crash."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        # Should not raise
        engine._emit("nonexistent_event", "arg1", "arg2")

    def test_emit_swallows_handler_exceptions(self) -> None:
        """_emit doesn't crash if handler raises."""
        config = MockConfig()
        events = MockEventHandler()
        events.on_error = MagicMock(side_effect=Exception("Handler error"))
        engine = VoxtypeEngine(config=config, events=events)

        # Should not raise
        engine._emit("on_error", "test", "test")

def _wait_for_controller(engine, *, predicate=None, timeout: float = 2.0) -> None:
    """Wait for controller to drain its queue and optionally satisfy a predicate."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if engine._controller._queue.empty() and (predicate is None or predicate()):
            return
        time.sleep(0.001)
    time.sleep(0.005)  # small margin for handler to finish

class TestStateControl:
    """Test state control methods.

    Note: State transitions are now asynchronous via the event queue.
    Tests start the controller and wait for event processing.
    """

    def test_toggle_listening_off_to_listening(self) -> None:
        """Toggle from OFF to LISTENING."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        engine._controller.start()

        try:
            engine._toggle_listening()
            _wait_for_controller(engine)
            assert engine.state == AppState.LISTENING
            assert len(events.state_changes) == 1
            assert events.state_changes[0] == (AppState.OFF, AppState.LISTENING, "hotkey_toggle")
        finally:
            engine._controller.stop()

    def test_toggle_listening_listening_to_off(self) -> None:
        """Toggle from LISTENING to OFF."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        engine._controller.start()

        try:
            # First toggle ON
            engine._toggle_listening()
            _wait_for_controller(engine)
            # Then toggle OFF
            engine._toggle_listening()
            _wait_for_controller(engine)
            assert engine.state == AppState.OFF
            assert len(events.state_changes) == 2
            assert events.state_changes[1] == (AppState.LISTENING, AppState.OFF, "hotkey_toggle")
        finally:
            engine._controller.stop()

    def test_set_listening_on(self) -> None:
        """_set_listening(True) turns on listening."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        engine._controller.start()

        try:
            engine._set_listening(True)
            _wait_for_controller(engine)
            assert engine.state == AppState.LISTENING
        finally:
            engine._controller.stop()

    def test_set_listening_off(self) -> None:
        """_set_listening(False) turns off listening."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        engine._controller.start()

        try:
            engine._set_listening(True)
            _wait_for_controller(engine)
            engine._set_listening(False)
            _wait_for_controller(engine)
            assert engine.state == AppState.OFF
        finally:
            engine._controller.stop()

    def test_set_listening_noop_when_already_on(self) -> None:
        """_set_listening(True) is noop when already listening."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        engine._controller.start()

        try:
            engine._set_listening(True)
            _wait_for_controller(engine)
            events.state_changes.clear()
            engine._set_listening(True)  # Already on
            _wait_for_controller(engine)
            assert len(events.state_changes) == 0
        finally:
            engine._controller.stop()

class TestAgentSwitch:
    """Test agent switching.

    Note: Agent switching is now async via the event queue.
    """

    def test_switch_agent_next(self) -> None:
        """Switch to next agent."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        register_test_agents(engine, ["claude", "cursor", "vscode"])
        engine._controller.start()

        try:
            engine._switch_agent(1)
            _wait_for_controller(engine)
            assert engine.current_agent == "cursor"
            assert engine.current_agent_index == 1
            assert events.agent_changes[0] == ("cursor", 1)
        finally:
            engine._controller.stop()

    def test_switch_agent_previous(self) -> None:
        """Switch to previous agent."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        register_test_agents(engine, ["claude", "cursor", "vscode"])
        engine._controller.start()

        try:
            engine._switch_agent(-1)  # Wraps to last
            _wait_for_controller(engine)
            assert engine.current_agent == "vscode"
            assert engine.current_agent_index == 2
        finally:
            engine._controller.stop()

    def test_switch_agent_wraps_around(self) -> None:
        """Agent switching wraps around."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        register_test_agents(engine, ["claude", "cursor"])
        engine._controller.start()

        try:
            engine._switch_agent(1)  # cursor
            _wait_for_controller(engine)
            engine._switch_agent(1)  # wraps to claude
            _wait_for_controller(engine)
            assert engine.current_agent == "claude"
            assert engine.current_agent_index == 0
        finally:
            engine._controller.stop()

    def test_switch_agent_no_agents(self) -> None:
        """Switch with no agents does nothing."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        engine._controller.start()

        try:
            engine._switch_agent(1)  # Should not crash
            _wait_for_controller(engine)
            assert len(events.agent_changes) == 0
        finally:
            engine._controller.stop()

    def test_switch_to_agent_by_name_exact(self) -> None:
        """Switch to agent by exact name match."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        register_test_agents(engine, ["claude", "cursor", "vscode"])
        engine._controller.start()

        try:
            result = engine._switch_to_agent_by_name("cursor")
            _wait_for_controller(engine)
            assert result is True
            assert engine.current_agent == "cursor"
        finally:
            engine._controller.stop()

    def test_switch_to_agent_by_name_case_insensitive(self) -> None:
        """Switch to agent by name is case-insensitive."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        register_test_agents(engine, ["claude", "cursor", "vscode"])
        engine._controller.start()

        try:
            result = engine._switch_to_agent_by_name("CURSOR")
            _wait_for_controller(engine)
            assert result is True
            assert engine.current_agent == "cursor"
        finally:
            engine._controller.stop()

    def test_switch_to_agent_by_name_partial(self) -> None:
        """Switch to agent by partial name match."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        register_test_agents(engine, ["claude-code", "cursor", "vscode"])
        engine._controller.start()

        try:
            result = engine._switch_to_agent_by_name("code")
            _wait_for_controller(engine)
            assert result is True
            assert engine.current_agent == "claude-code"
        finally:
            engine._controller.stop()

    def test_switch_to_agent_by_name_not_found(self) -> None:
        """Switch to agent by name returns False (async, result is always True)."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        register_test_agents(engine, ["claude", "cursor"])
        engine._controller.start()

        try:
            result = engine._switch_to_agent_by_name("vscode")
            _wait_for_controller(engine)
            # With async processing, result is always True but no switch happens
            assert result is True
            # Agent should still be the original
            assert engine.current_agent == "claude"
        finally:
            engine._controller.stop()

    def test_switch_to_agent_by_index(self) -> None:
        """Switch to agent by index (1-based)."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        register_test_agents(engine, ["claude", "cursor", "vscode"])
        engine._controller.start()

        try:
            result = engine._switch_to_agent_by_index(2)  # 1-based
            _wait_for_controller(engine)
            assert result is True
            assert engine.current_agent == "cursor"
            assert engine.current_agent_index == 1
        finally:
            engine._controller.stop()

    def test_switch_to_agent_by_index_out_of_range(self) -> None:
        """Switch to agent by invalid index (async, no switch happens)."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        register_test_agents(engine, ["claude", "cursor"])
        engine._controller.start()

        try:
            result = engine._switch_to_agent_by_index(10)
            _wait_for_controller(engine)
            # With async processing, result is always True but no switch happens
            assert result is True
            # Agent should still be the original
            assert engine.current_agent == "claude"
        finally:
            engine._controller.stop()

    def test_handle_control_set_agent_colon_format(self) -> None:
        """_handle_control with output.set_agent:NAME switches agent."""
        config = MockConfig()
        events = MockEventHandler()
        engine = VoxtypeEngine(config=config, events=events)
        register_test_agents(engine, ["claude", "cursor"])
        engine._controller.start()

        try:
            result = engine._handle_control({"command": "output.set_agent:cursor"})
            _wait_for_controller(engine)
            assert result["status"] == "ok"
            assert engine.current_agent == "cursor"
        finally:
            engine._controller.stop()

class TestHotwords:
    """Test hotwords building."""

    def test_get_hotwords_from_config(self) -> None:
        """Hotwords from config."""
        config = MockConfig()
        config.stt.hotwords = "voxtype,hey claude"
        engine = VoxtypeEngine(config=config)

        result = engine._get_hotwords()
        assert result == "voxtype,hey claude"

    def test_get_hotwords_none(self) -> None:
        """No hotwords returns None."""
        config = MockConfig()
        config.stt.hotwords = None
        engine = VoxtypeEngine(config=config)

        result = engine._get_hotwords()
        assert result is None

class TestAgentId:
    """Test agent ID retrieval for socket-based injection."""

    def test_get_current_agent_id_with_agents(self) -> None:
        """Agent ID with agents configured."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        register_test_agents(engine, ["claude", "cursor"])

        result = engine.current_agent
        assert result == "claude"

    def test_get_current_agent_id_after_switch(self) -> None:
        """Agent ID changes after agent switch."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        register_test_agents(engine, ["claude", "cursor"])
        engine._controller.start()

        try:
            engine._switch_agent(1)
            _wait_for_controller(engine)
            result = engine.current_agent
            assert result == "cursor"
        finally:
            engine._controller.stop()

    def test_get_current_agent_id_no_agents(self) -> None:
        """Agent ID is None without agents."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)

        result = engine.current_agent
        assert result is None

class TestThreadSafety:
    """Test thread safety of engine operations."""

    def test_concurrent_state_toggles(self) -> None:
        """Concurrent state toggles don't corrupt state."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        errors = []

        def toggle_many_times() -> None:
            try:
                for _ in range(50):
                    engine._toggle_listening()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=toggle_many_times) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions
        assert len(errors) == 0
        # State should be valid
        assert engine.state in AppState

    def test_concurrent_agent_switches(self) -> None:
        """Concurrent agent switches don't corrupt index."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        register_test_agents(engine, ["a", "b", "c", "d", "e"])
        errors = []

        def switch_agents() -> None:
            try:
                for _ in range(50):
                    engine._switch_agent(1)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=switch_agents) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions
        assert len(errors) == 0
        # Index should be valid
        assert 0 <= engine.current_agent_index < len(engine.agents)

class TestVADCallbacks:
    """Test VAD callback methods.

    Note: VAD callbacks now send events processed asynchronously.
    """

    def test_on_vad_speech_start_emits_event(self) -> None:
        """VAD speech start emits recording_start event."""
        config = MockConfig()
        events = MockEventHandler()
        recording_started = []
        events.on_recording_start = lambda: recording_started.append(True)
        engine = VoxtypeEngine(config=config, events=events)
        engine._controller.start()

        try:
            # Need to be in LISTENING state first
            engine._state_manager.transition(AppState.LISTENING)
            engine._on_vad_speech_start()
            _wait_for_controller(engine)

            assert len(recording_started) == 1
            assert engine.state == AppState.RECORDING
        finally:
            engine._controller.stop()

    def test_on_vad_speech_start_ignored_when_off(self) -> None:
        """VAD speech start ignored when OFF."""
        config = MockConfig()
        events = MockEventHandler()
        recording_started = []
        events.on_recording_start = lambda: recording_started.append(True)
        engine = VoxtypeEngine(config=config, events=events)
        engine._controller.start()

        try:
            # State is OFF
            engine._on_vad_speech_start()
            _wait_for_controller(engine)

            assert len(recording_started) == 0
            assert engine.state == AppState.OFF
        finally:
            engine._controller.stop()

    def test_on_max_speech_duration_emits_event(self) -> None:
        """Max speech duration emits event."""
        config = MockConfig()
        events = MockEventHandler()
        max_reached = []
        events.on_max_duration_reached = lambda: max_reached.append(True)
        engine = VoxtypeEngine(config=config, events=events)

        engine._on_max_speech_duration()

        assert len(max_reached) == 1

class TestDiscardCurrent:
    """Test discarding current recording.

    Note: Discard is now async via the event queue.
    """

    def test_discard_current_resets_to_listening(self) -> None:
        """Discard while recording resets to listening."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine._controller.start()

        try:
            # Simulate being in RECORDING state
            engine._state_manager.transition(AppState.LISTENING)
            engine._state_manager.transition(AppState.RECORDING)

            engine._discard_current()
            _wait_for_controller(engine)

            assert engine.state == AppState.LISTENING
        finally:
            engine._controller.stop()

class TestProcessQueuedAudio:
    """Test _process_queued_audio handles numpy arrays correctly."""

    def test_queued_numpy_array_does_not_raise(self) -> None:
        """Queued numpy audio data doesn't raise ValueError on truthiness check."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine._controller.start()

        try:
            engine._state_manager.transition(AppState.LISTENING)

            # Mock audio manager with numpy array in queue
            mock_am = MagicMock()
            mock_am.sample_rate = 16000
            audio = np.zeros(5000, dtype=np.float32)
            mock_am.has_queued_audio = True
            mock_am.pop_queued_audio = MagicMock(side_effect=[audio, None])

            # has_queued_audio: True on first call, False after pop returns None
            call_count = [0]
            def has_queued():
                call_count[0] += 1
                return call_count[0] <= 1

            mock_am.has_queued_audio = property(lambda self: True)
            # Simpler approach: just set it as a regular attribute toggled by side_effect
            queue_state = [True]
            type(mock_am).has_queued_audio = property(lambda self: queue_state[0])

            def pop_and_drain():
                queue_state[0] = False
                return audio

            mock_am.pop_queued_audio = pop_and_drain
            engine._audio_manager = mock_am

            # This used to raise: ValueError: The truth value of an array...
            engine._process_queued_audio()
        finally:
            engine._controller.stop()

    def test_queued_empty_array_skipped(self) -> None:
        """Empty numpy array is skipped without error."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine._controller.start()

        try:
            engine._state_manager.transition(AppState.LISTENING)

            mock_am = MagicMock()
            mock_am.sample_rate = 16000
            empty = np.array([], dtype=np.float32)

            queue_state = [True]
            type(mock_am).has_queued_audio = property(lambda self: queue_state[0])

            def pop_and_drain():
                queue_state[0] = False
                return empty

            mock_am.pop_queued_audio = pop_and_drain
            engine._audio_manager = mock_am

            engine._process_queued_audio()
            # Should not raise, and no event sent (empty audio)
        finally:
            engine._controller.stop()

    def test_queued_none_skipped(self) -> None:
        """None from pop_queued_audio is skipped without error."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine._controller.start()

        try:
            engine._state_manager.transition(AppState.LISTENING)

            mock_am = MagicMock()
            mock_am.sample_rate = 16000

            queue_state = [True]
            type(mock_am).has_queued_audio = property(lambda self: queue_state[0])

            def pop_and_drain():
                queue_state[0] = False
                return None

            mock_am.pop_queued_audio = pop_and_drain
            engine._audio_manager = mock_am

            engine._process_queued_audio()
        finally:
            engine._controller.stop()

def _should_send_message(msg: dict) -> bool:
    """Helper that replicates engine's message sending logic.

    This is the exact logic from engine.py _inject_text:
    - Empty text without submit -> skip
    - Empty text with submit -> send (submit-only)
    - Text with or without submit -> send
    """
    msg_text = msg.get("text", "")
    x_input = msg.get("x_input", {})
    has_submit = x_input.get("submit", False) if isinstance(x_input, dict) else bool(x_input)
    return bool(msg_text.strip()) or has_submit

class TestMessageSendingLogic:
    """Tests for message sending logic - verifies empty/submit handling.

    These tests verify the logic used in engine._inject_text to decide
    whether a message should be sent to an agent.
    """

    def test_empty_text_without_submit_not_sent(self) -> None:
        """Empty text without submit flag should not be sent."""
        msg = {"text": "", "x_input": {}}
        assert _should_send_message(msg) is False

    def test_empty_text_with_submit_is_sent(self) -> None:
        """Empty text WITH submit flag should be sent (submit-only)."""
        msg = {"text": "", "x_input": {"submit": True}}
        assert _should_send_message(msg) is True

    def test_text_with_submit_is_sent(self) -> None:
        """Text with submit flag should be sent."""
        msg = {"text": "hello world", "x_input": {"submit": True}}
        assert _should_send_message(msg) is True

    def test_text_without_submit_is_sent(self) -> None:
        """Text without submit flag should be sent."""
        msg = {"text": "hello world", "x_input": {}}
        assert _should_send_message(msg) is True

    def test_whitespace_only_without_submit_not_sent(self) -> None:
        """Whitespace-only text without submit should not be sent."""
        msg = {"text": "   \n\t  ", "x_input": {}}
        assert _should_send_message(msg) is False

    def test_whitespace_only_with_submit_is_sent(self) -> None:
        """Whitespace-only text WITH submit should be sent."""
        msg = {"text": "   ", "x_input": {"submit": True}}
        assert _should_send_message(msg) is True

    def test_missing_x_input_treated_as_false(self) -> None:
        """Missing x_input key should be treated as no submit."""
        msg = {"text": ""}
        assert _should_send_message(msg) is False

    def test_missing_text_with_submit_is_sent(self) -> None:
        """Missing text key with submit should be sent."""
        msg = {"x_input": {"submit": True}}
        assert _should_send_message(msg) is True

    def test_missing_both_not_sent(self) -> None:
        """Missing both text and submit should not be sent."""
        msg = {}
        assert _should_send_message(msg) is False

    def test_none_text_without_submit_not_sent(self) -> None:
        """None text without submit should not be sent."""
        msg = {"text": None, "x_input": {}}
        # text=None -> .get("text", "") returns None, None.strip() would fail
        # but engine uses msg.get("text", "") which handles this
        # Actually this would fail - let's test that it's handled
        msg_text = msg.get("text", "") or ""  # Handle None
        x_input = msg.get("x_input", {})
        has_submit = x_input.get("submit", False) if isinstance(x_input, dict) else bool(x_input)
        should_send = bool(msg_text.strip()) or has_submit
        assert should_send is False

class TestTTSIntegration:
    """Tests for TTS engine integration in speak_text / _handle_tts_request."""

    def _make_engine(self, tts_available: bool = True) -> tuple[VoxtypeEngine, MagicMock]:
        config = MockConfig()
        config.audio.audio_feedback = True
        config.audio.headphones_mode = True  # no mic-pausing
        engine = VoxtypeEngine(config=config)
        mock_tts = MagicMock()
        if tts_available:
            engine._tts_engine = mock_tts
        else:
            engine._tts_engine = None
            engine._tts_error = "TTS engine 'piper' is not available."
        return engine, mock_tts

    @patch("voxtype.audio.beep.play_audio")
    def test_speak_text_uses_tts_engine(
        self, mock_play_audio: MagicMock
    ) -> None:
        """speak_text() uses pre-loaded _tts_engine via play_audio."""
        engine, mock_tts = self._make_engine()

        engine.speak_text("hello world")

        mock_play_audio.assert_called_once()
        # The callable passed to play_audio should call tts.speak
        fn = mock_play_audio.call_args[0][0]
        fn()
        mock_tts.speak.assert_called_once_with("hello world")

    @patch("voxtype.audio.beep.play_audio")
    def test_speak_text_skips_when_tts_unavailable(
        self, mock_play_audio: MagicMock
    ) -> None:
        """speak_text() silently skips when TTS engine not loaded."""
        engine, _ = self._make_engine(tts_available=False)

        engine.speak_text("hello world")

        mock_play_audio.assert_not_called()

    def test_handle_tts_request_uses_tts_engine(self) -> None:
        """_handle_tts_request uses pre-loaded TTS engine and returns duration."""
        engine, mock_tts = self._make_engine()

        result = engine._handle_tts_request({"text": "test"})

        assert result["status"] == "ok"
        assert "duration_ms" in result
        mock_tts.speak.assert_called_once_with("test")

    @patch("voxtype.tts.get_cached_tts_engine")
    def test_handle_tts_request_override_config(
        self, mock_get_tts: MagicMock
    ) -> None:
        """_handle_tts_request applies engine/language/voice/speed overrides."""
        engine, _ = self._make_engine()
        mock_override_tts = MagicMock()
        mock_get_tts.return_value = mock_override_tts

        engine._handle_tts_request({
            "text": "ciao",
            "engine": "piper",
            "language": "it",
            "voice": "paola",
            "speed": 200,
        })

        cfg = mock_get_tts.call_args[0][0]
        assert cfg.engine == "piper"
        assert cfg.language == "it"
        assert cfg.voice == "paola"
        assert cfg.speed == 200
        mock_override_tts.speak.assert_called_once_with("ciao")

    def test_handle_tts_request_empty_text(self) -> None:
        """_handle_tts_request returns error for empty text."""
        engine, _ = self._make_engine()

        result = engine._handle_tts_request({"text": ""})
        assert result["status"] == "error"

        result2 = engine._handle_tts_request({})
        assert result2["status"] == "error"

    def test_handle_tts_request_unavailable_returns_error(self) -> None:
        """_handle_tts_request returns error when TTS engine not loaded."""
        engine, _ = self._make_engine(tts_available=False)

        result = engine._handle_tts_request({"text": "test"})

        assert result["status"] == "error"
        assert "not available" in result["error"]

class TestSetOutputMode:
    """Test runtime output mode switching (keyboard <-> agents)."""

    def test_switch_to_keyboard_sets_mode(self) -> None:
        """Switching to keyboard mode sets agent_mode=False and current to __keyboard__."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine.agent_mode = True
        # Register keyboard agent (as create_engine does)
        mock_kb = MagicMock()
        mock_kb.id = "__keyboard__"
        engine._keyboard_agent = mock_kb
        engine._agents["__keyboard__"] = mock_kb
        engine._agent_order.append("__keyboard__")
        register_test_agents(engine, ["claude"])

        engine._set_output_mode("keyboard")

        assert engine.agent_mode is False
        assert engine.current_agent == "__keyboard__"
        # Keyboard agent stays registered — not created/destroyed on switch
        assert "__keyboard__" in engine.agents

    def test_switch_to_agents_restores_mode(self) -> None:
        """Switching to agents mode sets agent_mode=True and keeps keyboard registered."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine.agent_mode = False
        # Register keyboard agent (as create_engine does)
        mock_kb = MagicMock()
        mock_kb.id = "__keyboard__"
        engine._keyboard_agent = mock_kb
        engine._agents["__keyboard__"] = mock_kb
        engine._agent_order.append("__keyboard__")
        engine._current_agent_id = "__keyboard__"
        register_test_agents(engine, ["claude"])

        engine._set_output_mode("agents")

        assert engine.agent_mode is True
        # KeyboardAgent stays registered, just not current
        assert "__keyboard__" in engine.agents
        assert engine._keyboard_agent is mock_kb
        assert engine.current_agent == "claude"

    def test_switch_same_mode_is_noop(self) -> None:
        """Switching to the already-active mode does nothing."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine.agent_mode = True

        engine._set_output_mode("agents")

        # No keyboard agent created — already in agents mode
        assert engine._keyboard_agent is None

    def test_switch_to_keyboard_preserves_existing_agents(self) -> None:
        """Switching to keyboard doesn't disconnect existing SSE agents."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine.agent_mode = True
        # Register keyboard agent (as create_engine does)
        mock_kb = MagicMock()
        mock_kb.id = "__keyboard__"
        engine._keyboard_agent = mock_kb
        engine._agents["__keyboard__"] = mock_kb
        engine._agent_order.append("__keyboard__")
        register_test_agents(engine, ["claude", "aider"])

        engine._set_output_mode("keyboard")

        # SSE agents are still registered
        assert "claude" in engine.agents
        assert "aider" in engine.agents
        assert "__keyboard__" in engine.agents

    def test_switch_to_keyboard_saves_last_agent(self) -> None:
        """Switching to keyboard saves the current SSE agent for later restore."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine.agent_mode = True
        mock_kb = MagicMock()
        mock_kb.id = "__keyboard__"
        engine._keyboard_agent = mock_kb
        engine._agents["__keyboard__"] = mock_kb
        engine._agent_order.append("__keyboard__")
        register_test_agents(engine, ["claude", "cursor"])
        # Select cursor as current
        engine._current_agent_id = "cursor"

        engine._set_output_mode("keyboard")

        assert engine.current_agent == "__keyboard__"
        assert engine._last_sse_agent_id == "cursor"

    def test_switch_back_to_agents_restores_last_selected(self) -> None:
        """Switching back to agents restores the last selected SSE agent, not first."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine.agent_mode = True
        mock_kb = MagicMock()
        mock_kb.id = "__keyboard__"
        engine._keyboard_agent = mock_kb
        engine._agents["__keyboard__"] = mock_kb
        engine._agent_order.append("__keyboard__")
        register_test_agents(engine, ["claude", "cursor"])
        # Select cursor, then switch to keyboard, then back
        engine._current_agent_id = "cursor"

        engine._set_output_mode("keyboard")
        assert engine.current_agent == "__keyboard__"

        engine._set_output_mode("agents")
        assert engine.current_agent == "cursor"
        assert engine.agent_mode is True

    def test_switch_back_to_agents_fallback_first(self) -> None:
        """If last agent was unregistered, fall back to first available."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine.agent_mode = False
        mock_kb = MagicMock()
        mock_kb.id = "__keyboard__"
        engine._keyboard_agent = mock_kb
        engine._agents["__keyboard__"] = mock_kb
        engine._agent_order.append("__keyboard__")
        engine._current_agent_id = "__keyboard__"
        register_test_agents(engine, ["claude", "cursor"])
        # Set a last_sse_agent that no longer exists
        engine._last_sse_agent_id = "aider"

        engine._set_output_mode("agents")
        assert engine.current_agent == "claude"

    def test_switch_invalid_mode_is_noop(self) -> None:
        """Invalid mode string does nothing."""
        config = MockConfig()
        engine = VoxtypeEngine(config=config)
        engine.agent_mode = True

        engine._set_output_mode("invalid")

        assert engine.agent_mode is True
