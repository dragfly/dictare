"""Tests for StateController event queue architecture."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import numpy as np

from voxtype.core.controller import StateController
from voxtype.core.events import (
    AgentSwitchEvent,
    DiscardCurrentEvent,
    HotkeyToggleEvent,
    PlayCompleteEvent,
    PlayStartEvent,
    SetListeningEvent,
    SpeechEndEvent,
    SpeechStartEvent,
    TranscriptionCompleteEvent,
)
from voxtype.core.state import AppState, StateManager


def _wait(timeout: float = 0.15) -> None:
    """Wait for controller to process events."""
    time.sleep(timeout)


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

    def _inject_text(self, text: str, agent: Any = None) -> None:
        self.injections.append((text, agent))

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

        controller.send(HotkeyToggleEvent(source="test"))
        assert controller._queue.qsize() == 1


class TestSpeechEvents:
    """Test speech-related events."""

    def test_speech_start_transitions_to_recording(self) -> None:
        """SpeechStartEvent transitions LISTENING -> RECORDING."""
        sm = StateManager(initial_state=AppState.LISTENING)
        recording_started = []
        controller = StateController(
            sm,
            on_recording_start=lambda: recording_started.append(True),
        )
        controller.start()

        try:
            controller.send(SpeechStartEvent(source="vad"))
            _wait()

            assert sm.state == AppState.RECORDING
            assert len(recording_started) == 1
        finally:
            controller.stop()

    def test_speech_start_ignored_when_off(self) -> None:
        """SpeechStartEvent ignored when in OFF state."""
        sm = StateManager(initial_state=AppState.OFF)
        controller = StateController(sm)
        controller.start()

        try:
            controller.send(SpeechStartEvent(source="vad"))
            _wait()

            assert sm.state == AppState.OFF
        finally:
            controller.stop()

    def test_speech_end_starts_transcription(self) -> None:
        """SpeechEndEvent triggers transcription."""
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
                SpeechEndEvent(
                    audio_data=audio_data,
                    agent=mock_agent,
                    source="vad",
                )
            )
            _wait()

            assert sm.state == AppState.TRANSCRIBING
            assert len(engine.transcriptions) == 1
            assert engine.transcriptions[0][1] is mock_agent
        finally:
            controller.stop()

    def test_speech_end_too_short_ignored(self) -> None:
        """SpeechEndEvent with short audio returns to LISTENING."""
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

            controller.send(SpeechEndEvent(audio_data=audio_data, source="vad"))
            _wait()

            assert sm.state == AppState.LISTENING
            assert len(engine.transcriptions) == 0
            # Should have state change with "audio_too_short" trigger
            assert any(t == "audio_too_short" for _, _, t in state_changes)
        finally:
            controller.stop()


class TestTranscriptionComplete:
    """Test transcription completion events."""

    def test_transcription_complete_returns_to_listening(self) -> None:
        """TranscriptionCompleteEvent transitions back to LISTENING."""
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
                TranscriptionCompleteEvent(
                    text="Hello world",
                    agent=mock_agent,
                    source="stt",
                )
            )
            _wait()

            assert sm.state == AppState.LISTENING
            assert len(engine.injections) == 1
            assert engine.injections[0] == ("Hello world", mock_agent)
        finally:
            controller.stop()


class TestPlayEvents:
    """Test play-related events."""

    def test_play_start_transitions_to_playing(self) -> None:
        """PlayStartEvent transitions LISTENING -> PLAYING."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            # Get play ID first (like app.py does)
            play_id = controller.get_next_play_id()
            controller.send(PlayStartEvent(text="Hello", source="tts"))
            _wait()

            assert sm.state == AppState.PLAYING
            assert controller.play_in_progress is True
            assert controller._current_play_id == play_id
            engine._audio_manager.reset_vad.assert_called()
        finally:
            controller.stop()

    def test_play_complete_returns_to_listening(self) -> None:
        """PlayCompleteEvent transitions PLAYING -> LISTENING."""
        sm = StateManager(initial_state=AppState.PLAYING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        # Set play ID to simulate playback in progress
        controller._current_play_id = 1
        controller.start()

        try:
            # Send complete with matching ID
            controller.send(PlayCompleteEvent(play_id=1, source="tts"))
            _wait()

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
        # Set play ID to simulate playback in progress
        controller._current_play_id = 1
        controller.start()

        try:
            # User presses OFF during playback
            controller.send(HotkeyToggleEvent(source="hotkey"))
            _wait()

            # Should still be PLAYING (playback not finished)
            assert sm.state == AppState.PLAYING
            assert controller._desired_state_after_play == AppState.OFF

            # Playback completes with matching ID
            controller.send(PlayCompleteEvent(play_id=1, source="tts"))
            _wait()

            # Now should go to OFF (user intent preserved)
            assert sm.state == AppState.OFF
        finally:
            controller.stop()

    def test_transcription_during_play_deferred(self) -> None:
        """Transcription completing during playback doesn't interfere."""
        sm = StateManager(initial_state=AppState.PLAYING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        # Set play ID to simulate playback in progress
        controller._current_play_id = 1
        controller.start()

        try:
            # Transcription completes while audio is playing
            controller.send(
                TranscriptionCompleteEvent(text="test", source="stt")
            )
            _wait()

            # State should still be PLAYING
            assert sm.state == AppState.PLAYING
            # Text should still be injected
            assert len(engine.injections) == 1
        finally:
            controller.stop()

    def test_concurrent_play_only_last_triggers_transition(self) -> None:
        """Only the LAST play completion triggers state transition (rapid agent switching)."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            # Simulate rapid agent switching: play 1, 2, 3 start in quick succession
            play_id_1 = controller.get_next_play_id()
            controller.send(PlayStartEvent(text="Agent 1", source="tts"))
            _wait()

            assert controller._current_play_id == 1
            assert sm.state == AppState.PLAYING

            # Second play starts (agent switch while play 1 still playing)
            play_id_2 = controller.get_next_play_id()
            controller.send(PlayStartEvent(text="Agent 2", source="tts"))
            _wait()

            assert controller._current_play_id == 2  # Updated to latest

            # Third play starts
            play_id_3 = controller.get_next_play_id()
            controller.send(PlayStartEvent(text="Agent 3", source="tts"))
            _wait()

            assert controller._current_play_id == 3

            # Play 1 completes - should be IGNORED (not the last)
            controller.send(PlayCompleteEvent(play_id=play_id_1, source="tts"))
            _wait()

            assert sm.state == AppState.PLAYING  # Still playing!
            assert controller.play_in_progress is True

            # Play 2 completes - should be IGNORED (not the last)
            controller.send(PlayCompleteEvent(play_id=play_id_2, source="tts"))
            _wait()

            assert sm.state == AppState.PLAYING  # Still playing!
            assert controller.play_in_progress is True

            # Play 3 completes - THIS is the last one, should transition
            controller.send(PlayCompleteEvent(play_id=play_id_3, source="tts"))
            _wait()

            assert sm.state == AppState.LISTENING  # Now back to listening
            assert controller.play_in_progress is False
        finally:
            controller.stop()

    def test_transcription_during_play_while_transcribing(self) -> None:
        """Fix for STUCK in TRANSCRIBING: play starts while transcribing, then both complete.

        Scenario:
        1. User speaks → TRANSCRIBING
        2. User switches agent → play starts (but state stays TRANSCRIBING)
        3. Transcription completes → deferred (play_in_progress is True)
        4. Play completes → should transition TRANSCRIBING → LISTENING
        """
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            # Play starts while in TRANSCRIBING (agent switch during transcription)
            play_id = controller.get_next_play_id()
            controller.send(PlayStartEvent(text="Agent 2", source="tts"))
            _wait()

            # State stays TRANSCRIBING (play only transitions from LISTENING)
            assert sm.state == AppState.TRANSCRIBING
            assert controller.play_in_progress is True

            # Transcription completes while audio playing → deferred
            controller.send(TranscriptionCompleteEvent(text="test", source="stt"))
            _wait()

            # Still TRANSCRIBING (deferred)
            assert sm.state == AppState.TRANSCRIBING
            assert controller._pending_transcription is not None

            # Play completes → should transition to LISTENING
            controller.send(PlayCompleteEvent(play_id=play_id, source="tts"))
            _wait()

            # NOW should be LISTENING (not stuck in TRANSCRIBING)
            assert sm.state == AppState.LISTENING
            assert controller.play_in_progress is False
        finally:
            controller.stop()


class TestHotkeyEvents:
    """Test hotkey-related events."""

    def test_hotkey_toggle_off_to_listening(self) -> None:
        """HotkeyToggleEvent toggles OFF -> LISTENING."""
        sm = StateManager(initial_state=AppState.OFF)
        state_changes = []
        controller = StateController(
            sm,
            on_state_change=lambda o, n, t: state_changes.append((o, n, t)),
        )
        controller.start()

        try:
            controller.send(HotkeyToggleEvent(source="hotkey"))
            _wait()

            assert sm.state == AppState.LISTENING
            assert state_changes[-1] == (AppState.OFF, AppState.LISTENING, "hotkey_toggle")
        finally:
            controller.stop()

    def test_hotkey_toggle_listening_to_off(self) -> None:
        """HotkeyToggleEvent toggles LISTENING -> OFF."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(HotkeyToggleEvent(source="hotkey"))
            _wait()

            assert sm.state == AppState.OFF
        finally:
            controller.stop()


class TestAgentSwitchEvents:
    """Test agent switching events."""

    def test_agent_switch_by_direction(self) -> None:
        """AgentSwitchEvent switches agent by direction."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(AgentSwitchEvent(direction=1, source="api"))
            _wait()

            assert engine._current_agent_index == 1
            assert len(engine.agent_switches) == 1
            assert engine.agent_switches[0] == ("cursor", 1)
        finally:
            controller.stop()

    def test_agent_switch_by_name(self) -> None:
        """AgentSwitchEvent switches agent by name."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(AgentSwitchEvent(agent_name="vscode", source="api"))
            _wait()

            assert engine._current_agent_index == 2
        finally:
            controller.stop()

    def test_agent_switch_by_index(self) -> None:
        """AgentSwitchEvent switches agent by index (1-based)."""
        sm = StateManager(initial_state=AppState.LISTENING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(AgentSwitchEvent(agent_index=3, source="api"))
            _wait()

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
            controller.send(AgentSwitchEvent(direction=1, source="api"))
            _wait()

            engine._audio_manager.flush_vad.assert_called()
        finally:
            controller.stop()


class TestSetListeningEvent:
    """Test SetListeningEvent."""

    def test_set_listening_on(self) -> None:
        """SetListeningEvent(on=True) turns on listening."""
        sm = StateManager(initial_state=AppState.OFF)
        controller = StateController(sm)
        controller.start()

        try:
            controller.send(SetListeningEvent(on=True, source="api"))
            _wait()

            assert sm.state == AppState.LISTENING
        finally:
            controller.stop()

    def test_set_listening_off(self) -> None:
        """SetListeningEvent(on=False) turns off listening."""
        sm = StateManager(initial_state=AppState.LISTENING)
        controller = StateController(sm)
        controller.start()

        try:
            controller.send(SetListeningEvent(on=False, source="api"))
            _wait()

            assert sm.state == AppState.OFF
        finally:
            controller.stop()


class TestDiscardEvent:
    """Test DiscardCurrentEvent."""

    def test_discard_resets_to_listening(self) -> None:
        """DiscardCurrentEvent resets RECORDING -> LISTENING."""
        sm = StateManager(initial_state=AppState.RECORDING)
        engine = MockEngine()
        controller = StateController(sm)
        controller.set_engine(engine)
        controller.start()

        try:
            controller.send(DiscardCurrentEvent(source="api"))
            _wait()

            assert sm.state == AppState.LISTENING
            engine._audio_manager.reset_vad.assert_called()
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
            controller.send(HotkeyToggleEvent(source="1"))  # OFF -> LISTENING
            controller.send(HotkeyToggleEvent(source="2"))  # LISTENING -> OFF
            controller.send(HotkeyToggleEvent(source="3"))  # OFF -> LISTENING
            _wait(0.2)

            # Should process in order
            assert len(state_changes) == 3
            assert state_changes[0][1] == AppState.LISTENING
            assert state_changes[1][1] == AppState.OFF
            assert state_changes[2][1] == AppState.LISTENING
        finally:
            controller.stop()
