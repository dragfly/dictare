"""Tests for StateController event queue architecture."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import numpy as np

from voxtype.core.controller import StateController
from voxtype.core.fsm import (
    AppState,
    DiscardCurrent,
    HotkeyPressed,
    PlayCompleted,
    PlayStarted,
    SetListening,
    SpeechEnded,
    SpeechStarted,
    StateManager,
    SwitchAgent,
    TranscriptionCompleted,
)

def _wait_until(predicate, timeout: float = 2.0) -> None:
    """Poll until predicate is true (1ms interval, no fixed sleep)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.001)

def _drain(controller, timeout: float = 2.0) -> None:
    """Wait until controller queue is empty and processed."""
    _wait_until(lambda: controller._queue.empty(), timeout=timeout)
    # Small extra margin for the handler to finish after dequeue
    time.sleep(0.005)

class MockEngine:
    """Mock engine for testing controller."""

    def __init__(self) -> None:
        self._audio_manager = MagicMock()
        self._audio_manager.sample_rate = 16000
        self._audio_manager.queue_audio = MagicMock()
        self._audio_manager.flush_vad = MagicMock()
        self._audio_manager.reset_vad = MagicMock()
        self._audio_manager.clear_queue = MagicMock()

        self.agents = ["claude", "cursor", "vscode"]
        self._current_agent_index = 0

        self.transcriptions: list[Any] = []
        self.injections: list[Any] = []
        self.agent_switches: list[tuple[str, int]] = []

    def _transcribe_and_process(self, audio_data: Any, agent: Any = None) -> None:
        self.transcriptions.append((audio_data, agent))

    def _inject_text(self, text: str, agent: Any = None, language: str | None = None) -> None:
        self.injections.append((text, agent, language))

    def _process_queued_audio(self) -> None:
        pass

    def _discard_current_internal(self) -> None:
        self._audio_manager.clear_queue()
        self._audio_manager.reset_vad()

    def _switch_agent_internal(self, direction: int) -> None:
        self._current_agent_index = (self._current_agent_index + direction) % len(self.agents)
        self.agent_switches.append((self.agents[self._current_agent_index], self._current_agent_index))

    def _switch_to_agent_by_name_internal(self, name: str) -> bool:
        for i, agent in enumerate(self.agents):
            if agent.lower() == name.lower():
                self._current_agent_index = i
                self.agent_switches.append((agent, i))
                return True
        return False

    def _switch_to_agent_by_index_internal(self, index: int) -> bool:
        idx = index - 1
        if 0 <= idx < len(self.agents):
            self._current_agent_index = idx
            self.agent_switches.append((self.agents[idx], idx))
            return True
        return False

class TestControllerBasics:
    """Test basic controller functionality."""

    def test_start_stop(self) -> None:
        """Controller starts and stops cleanly."""
        sm = StateManager(initial_state=AppState.OFF)
        controller = StateController(sm)

        controller.start()
        assert controller._running is True
        assert controller._worker is not None

        controller.stop()
        assert controller._running is False

    def test_send_event(self) -> None:
        """Events can be sent to the queue."""
        sm = StateManager(initial_state=AppState.OFF)
        controller = StateController(sm)

        controller.send(HotkeyPressed(source="test"))
        assert controller._queue.qsize() == 1

class TestSpeechEvents:
    """Test speech-related events."""

    def test_speech_start_transitions_to_recording(self) -> None:
        """SpeechStarted transitions LISTENING -> RECORDING."""
        sm = StateManager(initial_state=AppState.LISTENING)
        recording_started = []
        controller = StateController(
            sm,
            on_recording_start=lambda: recording_started.append(True),
        )
        controller.start()

        try:
            controller.send(SpeechStarted(source="vad"))
            _wait_until(lambda: sm.state == AppState.RECORDING)

            assert sm.state == AppState.RECORDING
            assert len(recording_started) == 1
        finally:
            controller.stop()

    def test_speech_start_ignored_when_off(self) -> None:
        """SpeechStarted ignored when in OFF state."""
        sm = StateManager(initial_state=AppState.OFF)
        controller = StateController(sm)
        controller.start()

        try:
            controller.send(SpeechStarted(source="vad"))
            _drain(controller)

            assert sm.state == AppState.OFF
        finally:
            controller.stop()

    def test_speech_end_starts_transcription(self) -> None:
        """SpeechEnded triggers transcription."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            # Create audio data with enough samples (> 300ms at 16kHz = 4800 samples)
            audio_data = np.zeros(5000, dtype=np.float32)
            mock_agent = MagicMock()

            controller.send(
                SpeechEnded(
                    audio_data=audio_data,
                    agent=mock_agent,
                    source="vad",
                )
            )
            _wait_until(lambda: sm.state == AppState.TRANSCRIBING)

            assert sm.state == AppState.TRANSCRIBING
            assert len(engine.transcriptions) == 1
            assert engine.transcriptions[0][1] is mock_agent
        finally:
            controller.stop()

    def test_speech_end_too_short_ignored(self) -> None:
        """SpeechEnded with short audio returns to LISTENING."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        state_changes = []
        controller = StateController(
            sm,
            on_state_change=lambda o, n, t: state_changes.append((o, n, t)),
        )
        controller.set_engine(engine)
        controller.start()

        try:
            # Audio too short (< 300ms at 16kHz = 4800 samples)
            audio_data = np.zeros(1000, dtype=np.float32)

            controller.send(SpeechEnded(audio_data=audio_data, source="vad"))
            _wait_until(lambda: any(t == "audio_too_short" for _, _, t in state_changes))

            assert sm.state == AppState.LISTENING
            assert len(engine.transcriptions) == 0
            assert any(t == "audio_too_short" for _, _, t in state_changes)
        finally:
            controller.stop()

class TestSpeechEndQueuesAudio:
    """Test speech queuing during TRANSCRIBING and INJECTING."""

    def test_speech_end_during_transcribing_queues_audio(self) -> None:
        """SpeechEnded during TRANSCRIBING queues audio for later."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            audio_data = np.zeros(5000, dtype=np.float32)
            controller.send(SpeechEnded(audio_data=audio_data, source="vad"))
            _drain(controller)

            assert sm.state == AppState.TRANSCRIBING
            engine._audio_manager.queue_audio.assert_called_once_with(audio_data)
        finally:
            controller.stop()

    def test_speech_end_during_injecting_queues_audio(self) -> None:
        """SpeechEnded during INJECTING queues audio for later."""
        sm = StateManager(initial_state=AppState.INJECTING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            audio_data = np.zeros(5000, dtype=np.float32)
            controller.send(SpeechEnded(audio_data=audio_data, source="vad"))
            _drain(controller)

            assert sm.state == AppState.INJECTING
            engine._audio_manager.queue_audio.assert_called_once_with(audio_data)
        finally:
            controller.stop()

    def test_speech_end_without_engine_does_not_crash(self) -> None:
        """SpeechEnded in busy state without engine doesn't crash."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        controller = StateController(sm)
        controller.start()

        try:
            audio_data = np.zeros(5000, dtype=np.float32)
            controller.send(SpeechEnded(audio_data=audio_data, source="vad"))
            _drain(controller)

            assert sm.state == AppState.TRANSCRIBING
        finally:
            controller.stop()

class TestTranscriptionComplete:
    """Test transcription completion events."""

    def test_transcription_complete_returns_to_listening(self) -> None:
        """TranscriptionCompleted transitions back to LISTENING."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        engine = MockEngine()
        state_changes = []
        controller = StateController(
            sm,
            on_state_change=lambda o, n, t: state_changes.append((o, n, t)),
        )
        controller.set_engine(engine)
        controller.start()

        try:
            mock_agent = MagicMock()
            controller.send(
                TranscriptionCompleted(
                    text="Hello world",
                    agent=mock_agent,
                    source="stt",
                )
            )
            _wait_until(lambda: sm.state == AppState.LISTENING)

            assert sm.state == AppState.LISTENING
            assert len(engine.injections) == 1
            assert engine.injections[0] == ("Hello world", mock_agent, None)
        finally:
            controller.stop()

class TestPlayEvents:
    """Test play-related events."""

    def test_play_start_transitions_to_playing(self) -> None:
        """PlayStarted transitions LISTENING -> PLAYING."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            play_id = controller.get_next_play_id()
            controller.send(PlayStarted(text="Hello", source="tts"))
            _wait_until(lambda: sm.state == AppState.PLAYING)

            assert sm.state == AppState.PLAYING
            assert controller.play_in_progress is True
            assert controller._current_play_id == play_id
            engine._audio_manager.reset_vad.assert_called()
        finally:
            controller.stop()

    def test_play_complete_returns_to_listening(self) -> None:
        """PlayCompleted transitions PLAYING -> LISTENING."""
        sm = StateManager(initial_state=AppState.PLAYING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller._current_play_id = 1
        controller.start()

        try:
            controller.send(PlayCompleted(play_id=1, source="tts"))
            _wait_until(lambda: sm.state == AppState.LISTENING)

            assert sm.state == AppState.LISTENING
            assert controller.play_in_progress is False
        finally:
            controller.stop()

    def test_hotkey_off_during_play_deferred(self) -> None:
        """Pressing OFF during playback defers transition until play completes."""
        sm = StateManager(initial_state=AppState.PLAYING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller._current_play_id = 1
        controller.start()

        try:
            controller.send(HotkeyPressed(source="hotkey"))
            _wait_until(lambda: controller._desired_state_after_play == AppState.OFF)

            assert sm.state == AppState.PLAYING
            assert controller._desired_state_after_play == AppState.OFF

            controller.send(PlayCompleted(play_id=1, source="tts"))
            _wait_until(lambda: sm.state == AppState.OFF)

            assert sm.state == AppState.OFF
        finally:
            controller.stop()

    def test_transcription_during_play_deferred(self) -> None:
        """Transcription completing during playback doesn't interfere."""
        sm = StateManager(initial_state=AppState.PLAYING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller._current_play_id = 1
        controller.start()

        try:
            controller.send(
                TranscriptionCompleted(text="test", source="stt")
            )
            _wait_until(lambda: len(engine.injections) == 1)

            assert sm.state == AppState.PLAYING
            assert len(engine.injections) == 1
        finally:
            controller.stop()

    def test_concurrent_play_only_last_triggers_transition(self) -> None:
        """Only the LAST play completion triggers state transition."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            # Play 1 starts
            play_id_1 = controller.get_next_play_id()
            controller.send(PlayStarted(text="Agent 1", source="tts"))
            _wait_until(lambda: sm.state == AppState.PLAYING)

            assert controller._current_play_id == 1

            # Play 2 starts
            play_id_2 = controller.get_next_play_id()
            controller.send(PlayStarted(text="Agent 2", source="tts"))
            _wait_until(lambda: controller._current_play_id == 2)

            # Play 3 starts
            play_id_3 = controller.get_next_play_id()
            controller.send(PlayStarted(text="Agent 3", source="tts"))
            _wait_until(lambda: controller._current_play_id == 3)

            # Play 1 completes - should be IGNORED
            controller.send(PlayCompleted(play_id=play_id_1, source="tts"))
            _drain(controller)

            assert sm.state == AppState.PLAYING
            assert controller.play_in_progress is True

            # Play 2 completes - should be IGNORED
            controller.send(PlayCompleted(play_id=play_id_2, source="tts"))
            _drain(controller)

            assert sm.state == AppState.PLAYING
            assert controller.play_in_progress is True

            # Play 3 completes - THIS triggers transition
            controller.send(PlayCompleted(play_id=play_id_3, source="tts"))
            _wait_until(lambda: sm.state == AppState.LISTENING)

            assert sm.state == AppState.LISTENING
            assert controller.play_in_progress is False
        finally:
            controller.stop()

    def test_transcription_during_play_while_transcribing(self) -> None:
        """Play starts while transcribing, then both complete."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            # Play starts while in TRANSCRIBING
            play_id = controller.get_next_play_id()
            controller.send(PlayStarted(text="Agent 2", source="tts"))
            _wait_until(lambda: controller.play_in_progress is True)

            assert sm.state == AppState.TRANSCRIBING

            # Transcription completes while audio playing → deferred
            controller.send(TranscriptionCompleted(text="test", source="stt"))
            _wait_until(lambda: controller._pending_transcription is not None)

            assert sm.state == AppState.TRANSCRIBING

            # Play completes → should transition to LISTENING
            controller.send(PlayCompleted(play_id=play_id, source="tts"))
            _wait_until(lambda: sm.state == AppState.LISTENING)

            assert sm.state == AppState.LISTENING
            assert controller.play_in_progress is False
        finally:
            controller.stop()

class TestHotkeyEvents:
    """Test hotkey-related events."""

    def test_hotkey_toggle_off_to_listening(self) -> None:
        """HotkeyPressed toggles OFF -> LISTENING."""
        sm = StateManager(initial_state=AppState.OFF)
        state_changes = []
        controller = StateController(
            sm,
            on_state_change=lambda o, n, t: state_changes.append((o, n, t)),
        )
        controller.start()

        try:
            controller.send(HotkeyPressed(source="hotkey"))
            _wait_until(lambda: sm.state == AppState.LISTENING)

            assert sm.state == AppState.LISTENING
            assert state_changes[-1] == (AppState.OFF, AppState.LISTENING, "hotkey_toggle")
        finally:
            controller.stop()

    def test_hotkey_toggle_listening_to_off(self) -> None:
        """HotkeyPressed toggles LISTENING -> OFF."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(HotkeyPressed(source="hotkey"))
            _wait_until(lambda: sm.state == AppState.OFF)

            assert sm.state == AppState.OFF
        finally:
            controller.stop()

class TestSwitchAgents:
    """Test agent switching events."""

    def test_agent_switch_by_direction(self) -> None:
        """SwitchAgent switches agent by direction."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(SwitchAgent(direction=1, source="api"))
            _wait_until(lambda: len(engine.agent_switches) == 1)

            assert engine._current_agent_index == 1
            assert engine.agent_switches[0] == ("cursor", 1)
        finally:
            controller.stop()

    def test_agent_switch_by_name(self) -> None:
        """SwitchAgent switches agent by name."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(SwitchAgent(agent_name="vscode", source="api"))
            _wait_until(lambda: engine._current_agent_index == 2)

            assert engine._current_agent_index == 2
        finally:
            controller.stop()

    def test_agent_switch_by_index(self) -> None:
        """SwitchAgent switches agent by index (1-based)."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(SwitchAgent(agent_index=3, source="api"))
            _wait_until(lambda: engine._current_agent_index == 2)

            assert engine._current_agent_index == 2  # vscode (0-indexed)
        finally:
            controller.stop()

    def test_agent_switch_flushes_vad(self) -> None:
        """Agent switch flushes VAD before switching."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(SwitchAgent(direction=1, source="api"))
            _wait_until(lambda: len(engine.agent_switches) == 1)

            engine._audio_manager.flush_vad.assert_called()
        finally:
            controller.stop()

class TestSetListening:
    """Test SetListening."""

    def test_set_listening_on(self) -> None:
        """SetListening(on=True) turns on listening."""
        sm = StateManager(initial_state=AppState.OFF)
        controller = StateController(sm)
        controller.start()

        try:
            controller.send(SetListening(on=True, source="api"))
            _wait_until(lambda: sm.state == AppState.LISTENING)

            assert sm.state == AppState.LISTENING
        finally:
            controller.stop()

    def test_set_listening_off(self) -> None:
        """SetListening(on=False) turns off listening."""
        sm = StateManager(initial_state=AppState.LISTENING)
        controller = StateController(sm)
        controller.start()

        try:
            controller.send(SetListening(on=False, source="api"))
            _wait_until(lambda: sm.state == AppState.OFF)

            assert sm.state == AppState.OFF
        finally:
            controller.stop()

class TestDiscardEvent:
    """Test DiscardCurrent."""

    def test_discard_resets_to_listening(self) -> None:
        """DiscardCurrent resets RECORDING -> LISTENING."""
        sm = StateManager(initial_state=AppState.RECORDING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(DiscardCurrent(source="api"))
            _wait_until(lambda: sm.state == AppState.LISTENING)

            assert sm.state == AppState.LISTENING
            engine._audio_manager.reset_vad.assert_called()
        finally:
            controller.stop()

class TestTranscriptionWatchdog:
    """Test transcription watchdog timer.

    Tests call _on_transcription_timeout() directly to verify logic
    without depending on real timers.
    """

    def test_timeout_handler_recovers_stuck_transcribing(self) -> None:
        """Timeout handler forces recovery when in TRANSCRIBING."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            # Directly invoke timeout — simulates watchdog firing
            controller._on_transcription_timeout()
            _wait_until(lambda: sm.state == AppState.LISTENING)

            assert sm.state == AppState.LISTENING
        finally:
            controller.stop()

    def test_timeout_handler_noop_if_not_transcribing(self) -> None:
        """Timeout handler does nothing if not in TRANSCRIBING."""
        sm = StateManager(initial_state=AppState.LISTENING)
        controller = StateController(sm)
        controller.start()

        try:
            controller._on_transcription_timeout()
            _drain(controller)

            assert sm.state == AppState.LISTENING
        finally:
            controller.stop()

    def test_speech_end_starts_watchdog(self) -> None:
        """SpeechEnded starts the watchdog timer."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.TRANSCRIPTION_TIMEOUT = 60  # Long — we just check it starts
        controller.start()

        try:
            audio_data = np.zeros(5000, dtype=np.float32)
            controller.send(SpeechEnded(audio_data=audio_data, source="vad"))
            _wait_until(lambda: sm.state == AppState.TRANSCRIBING)
            _wait_until(
                lambda: controller._transcription_watchdog is not None
                and controller._transcription_watchdog.is_alive()
            )

            assert controller._transcription_watchdog is not None
            assert controller._transcription_watchdog.is_alive()
        finally:
            controller.stop()

    def test_watchdog_cancelled_on_normal_completion(self) -> None:
        """Normal TranscriptionComplete cancels watchdog."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller._start_transcription_watchdog()
            assert controller._transcription_watchdog is not None

            controller.send(
                TranscriptionCompleted(text="hello", source="stt")
            )
            _wait_until(lambda: sm.state == AppState.LISTENING)

            assert controller._transcription_watchdog is None
        finally:
            controller.stop()

class TestEventOrdering:
    """Test FIFO event ordering."""

    def test_events_processed_in_order(self) -> None:
        """Events are processed in FIFO order."""
        sm = StateManager(initial_state=AppState.OFF)
        state_changes = []
        controller = StateController(
            sm,
            on_state_change=lambda o, n, t: state_changes.append((o, n, t)),
        )
        controller.start()

        try:
            # Send multiple events rapidly
            controller.send(HotkeyPressed(source="1"))  # OFF -> LISTENING
            controller.send(HotkeyPressed(source="2"))  # LISTENING -> OFF
            controller.send(HotkeyPressed(source="3"))  # OFF -> LISTENING
            _wait_until(lambda: len(state_changes) >= 3)

            assert len(state_changes) == 3
            assert state_changes[0][1] == AppState.LISTENING
            assert state_changes[1][1] == AppState.OFF
            assert state_changes[2][1] == AppState.LISTENING
        finally:
            controller.stop()

class TestAudioFeedbackSounds:
    """Test audio feedback sound files and config."""

    def test_transcribing_sound_exists(self) -> None:
        """Bundled transcribing sound exists."""
        from voxtype.audio.beep import DEFAULT_SOUND_TRANSCRIBING

        assert DEFAULT_SOUND_TRANSCRIBING.exists()

    def test_ready_sound_exists(self) -> None:
        """Bundled ready sound exists."""
        from voxtype.audio.beep import DEFAULT_SOUND_READY

        assert DEFAULT_SOUND_READY.exists()

    def test_sound_configs_default_enabled(self) -> None:
        """AudioConfig sounds default to enabled with no custom path."""
        from voxtype.config import AudioConfig

        cfg = AudioConfig()
        for name in ("start", "stop", "transcribing", "ready", "sent", "agent_announce"):
            assert name in cfg.sounds
            assert cfg.sounds[name].enabled is True
            assert cfg.sounds[name].path is None

    def test_transcribing_transition_fires_callback(self) -> None:
        """RECORDING→TRANSCRIBING fires on_state_change callback."""
        from voxtype.audio.beep import DEFAULT_SOUND_TRANSCRIBING

        sm = StateManager(initial_state=AppState.RECORDING)
        engine = MockEngine()
        played = []

        controller = StateController(
            sm,
            on_state_change=lambda o, n, t: played.append((o, n)),
        )
        controller.set_engine(engine)
        controller.start()

        try:
            audio_data = np.zeros(5000, dtype=np.float32)
            controller.send(
                SpeechEnded(audio_data=audio_data, source="vad")
            )
            _wait_until(lambda: sm.state == AppState.TRANSCRIBING)

            assert any(n == AppState.TRANSCRIBING for _, n in played)
            assert DEFAULT_SOUND_TRANSCRIBING.suffix == ".wav"
        finally:
            controller.stop()

    def test_ready_feedback_played(self) -> None:
        """TRANSCRIBING→LISTENING triggers ready sound."""
        from voxtype.audio.beep import DEFAULT_SOUND_READY

        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        engine = MockEngine()
        played = []

        controller = StateController(
            sm,
            on_state_change=lambda o, n, t: played.append((o, n)),
        )
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(
                TranscriptionCompleted(text="hello", source="stt")
            )
            _wait_until(lambda: sm.state == AppState.LISTENING)

            assert any(
                o == AppState.TRANSCRIBING and n == AppState.LISTENING
                for o, n in played
            )
            assert DEFAULT_SOUND_READY.suffix == ".wav"
        finally:
            controller.stop()
