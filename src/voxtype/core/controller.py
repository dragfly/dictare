"""State Controller - Event Queue Architecture.

Single component responsible for all state transitions.
All other components send events to the queue.

This solves:
- Race conditions from multiple threads modifying state
- Lost user intent (e.g., pressing OFF during TTS)
- Inconsistent ordering of concurrent events
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from queue import Empty, Full, Queue
from typing import TYPE_CHECKING, Any

from voxtype.core.events import (
    AgentSwitchEvent,
    DiscardCurrentEvent,
    HotkeyDoubleTapEvent,
    HotkeyToggleEvent,
    SetListeningEvent,
    SpeechEndEvent,
    SpeechStartEvent,
    StateEvent,
    TranscriptionCompleteEvent,
    TTSCompleteEvent,
    TTSStartEvent,
)
from voxtype.core.state import AppState

if TYPE_CHECKING:
    from voxtype.core.state import StateManager

logger = logging.getLogger(__name__)

class StateController:
    """Processes events and manages state transitions.

    This is the ONLY component that calls state_manager.transition().
    All other components send events to the queue.

    FIFO processing - no priority. Simple model.
    """

    def __init__(
        self,
        state_manager: StateManager,
        *,
        on_recording_start: Callable[[], None] | None = None,
        on_recording_end: Callable[[float], None] | None = None,
        on_state_change: Callable[[AppState, AppState, str], None] | None = None,
        on_mode_change: Callable[[], None] | None = None,
        on_agent_change: Callable[[str, int], None] | None = None,
    ) -> None:
        """Initialize the state controller.

        Args:
            state_manager: The state machine to control
            on_recording_start: Callback when recording starts
            on_recording_end: Callback when recording ends (with duration_ms)
            on_state_change: Callback on state transitions (old, new, trigger)
            on_mode_change: Callback when processing mode changes
            on_agent_change: Callback when agent changes (name, index)
        """
        self._state_manager = state_manager
        # Bounded queue to prevent memory exhaustion under heavy load
        # 100 events should be plenty - events should process fast
        self._queue: Queue[StateEvent] = Queue(maxsize=100)
        self._running = False
        self._worker: threading.Thread | None = None

        # Callbacks for engine/app integration
        self._on_recording_start = on_recording_start
        self._on_recording_end = on_recording_end
        self._on_state_change = on_state_change
        self._on_mode_change = on_mode_change
        self._on_agent_change = on_agent_change

        # TTS state tracking with monotonic counter
        # Multiple TTS can play concurrently (e.g., rapid agent switching)
        # We only return to LISTENING when the LAST TTS completes
        self._current_tts_id: int = 0  # ID of the last TTS started (0 = none)
        self._desired_state_after_tts: AppState = AppState.LISTENING

        # Engine reference (set after creation via set_engine)
        self._engine: Any = None

        # Pending transcription during TTS
        self._pending_transcription: TranscriptionCompleteEvent | None = None

    def set_engine(self, engine: Any) -> None:
        """Set the engine reference for side effects.

        Called after engine creation to allow circular reference.
        """
        self._engine = engine

    def send(self, event: StateEvent) -> None:
        """Send event to queue. Thread-safe, non-blocking.

        Note:
            If queue is full (>100 events), logs warning and drops event.
            This prevents blocking senders under heavy load.
        """
        try:
            self._queue.put_nowait(event)
        except Full:
            logger.warning(f"Event queue full, dropping event: {type(event).__name__}")

    def start(self) -> None:
        """Start the event processing loop."""
        if self._running:
            return

        self._running = True
        self._worker = threading.Thread(
            target=self._process_loop,
            daemon=True,
            name="state-controller",
        )
        self._worker.start()

    def stop(self) -> None:
        """Stop the event processing loop."""
        self._running = False
        if self._worker:
            self._worker.join(timeout=1.0)
            self._worker = None

    @property
    def state(self) -> AppState:
        """Get current state (delegates to state manager)."""
        return self._state_manager.state

    @property
    def tts_in_progress(self) -> bool:
        """Check if TTS is currently playing."""
        return self._current_tts_id > 0

    def get_next_tts_id(self) -> int:
        """Get the next TTS ID. Called by app before starting TTS."""
        self._current_tts_id += 1
        return self._current_tts_id

    def _process_loop(self) -> None:
        """Main event processing loop."""
        while self._running:
            try:
                event = self._queue.get(timeout=0.1)
                self._handle_event(event)
            except Empty:
                continue
            except Exception as e:
                logger.exception(f"Error processing event: {e}")

    def _handle_event(self, event: StateEvent) -> None:
        """Handle a single event. Called sequentially, never concurrently."""
        if isinstance(event, SpeechStartEvent):
            self._handle_speech_start(event)
        elif isinstance(event, SpeechEndEvent):
            self._handle_speech_end(event)
        elif isinstance(event, TranscriptionCompleteEvent):
            self._handle_transcription_complete(event)
        elif isinstance(event, TTSStartEvent):
            self._handle_tts_start(event)
        elif isinstance(event, TTSCompleteEvent):
            self._handle_tts_complete(event)
        elif isinstance(event, HotkeyToggleEvent):
            self._handle_hotkey_toggle(event)
        elif isinstance(event, HotkeyDoubleTapEvent):
            self._handle_hotkey_double_tap(event)
        elif isinstance(event, AgentSwitchEvent):
            self._handle_agent_switch(event)
        elif isinstance(event, SetListeningEvent):
            self._handle_set_listening(event)
        elif isinstance(event, DiscardCurrentEvent):
            self._handle_discard_current(event)

    # =========================================================================
    # Event Handlers
    # =========================================================================

    def _handle_speech_start(self, event: SpeechStartEvent) -> None:
        """VAD detected speech."""
        if self._state_manager.state != AppState.LISTENING:
            return

        if self._state_manager.try_transition(AppState.RECORDING):
            if self._on_recording_start:
                self._on_recording_start()

    def _handle_speech_end(self, event: SpeechEndEvent) -> None:
        """VAD detected speech end, start transcription."""
        current = self._state_manager.state

        # Valid transitions: LISTENING or RECORDING → TRANSCRIBING
        if current not in (AppState.LISTENING, AppState.RECORDING):
            # Can't transition - queue audio if busy transcribing
            if current == AppState.TRANSCRIBING and self._engine:
                if self._engine._audio_manager:
                    self._engine._audio_manager.queue_audio(event.audio_data)
            return

        # Calculate duration
        sample_rate = 16000  # Default
        if self._engine and self._engine._audio_manager:
            sample_rate = self._engine._audio_manager.sample_rate
        duration_ms = len(event.audio_data) / sample_rate * 1000

        if not self._state_manager.try_transition(AppState.TRANSCRIBING):
            return

        if self._on_recording_end:
            self._on_recording_end(duration_ms)

        # Check minimum duration
        min_samples = int(sample_rate * 0.3)  # MIN_RECORDING_DURATION
        if len(event.audio_data) < min_samples:
            self._state_manager.reset_to_listening()
            if self._on_state_change:
                self._on_state_change(
                    AppState.TRANSCRIBING, AppState.LISTENING, "audio_too_short"
                )
            return

        # Start transcription (with captured injector)
        if self._engine:
            self._engine._transcribe_and_process(
                event.audio_data, injector=event.injector
            )

    def _handle_transcription_complete(self, event: TranscriptionCompleteEvent) -> None:
        """Transcription finished."""
        # If TTS is playing, defer the state transition
        if self.tts_in_progress:
            # Store for later processing when TTS completes
            self._pending_transcription = event
            # Still inject the text (goes to correct agent via captured injector)
            if self._engine and event.text:
                self._engine._inject_text(event.text, injector=event.injector)
            return

        # Normal flow: transition to LISTENING and inject
        old_state = self._state_manager.state
        self._state_manager.reset_to_listening()
        if self._on_state_change:
            self._on_state_change(old_state, AppState.LISTENING, "transcription_complete")

        if self._engine and event.text:
            self._engine._inject_text(event.text, injector=event.injector)

        # Process queued audio
        if self._engine:
            self._engine._process_queued_audio()

    def _handle_tts_start(self, event: TTSStartEvent) -> None:
        """TTS is about to play.

        Note: The TTS ID is assigned via get_next_tts_id() BEFORE sending this event.
        This handler just manages VAD and state transitions.
        """
        # Reset desired state for this new TTS (user might press OFF during it)
        self._desired_state_after_tts = AppState.LISTENING

        # Reset VAD to discard any buffered audio
        if self._engine and self._engine._audio_manager:
            self._engine._audio_manager.reset_vad()

        # Transition to PLAYING if in LISTENING
        if self._state_manager.state == AppState.LISTENING:
            old_state = self._state_manager.state
            if self._state_manager.try_transition(AppState.PLAYING):
                if self._on_state_change:
                    self._on_state_change(old_state, AppState.PLAYING, "tts_start")

    def _handle_tts_complete(self, event: TTSCompleteEvent) -> None:
        """TTS finished playing.

        Only processes if event.tts_id matches the LAST TTS started.
        This handles concurrent TTS (rapid agent switching) - we only
        return to LISTENING when the final TTS completes.
        """
        # Ignore if this is not the last TTS (concurrent TTS scenario)
        if event.tts_id != self._current_tts_id:
            return

        # This is the last TTS - clear the counter
        self._current_tts_id = 0

        # Reset VAD to discard TTS audio
        if self._engine and self._engine._audio_manager:
            self._engine._audio_manager.reset_vad()

        # Go to desired state (LISTENING or OFF based on user intent)
        target_state = self._desired_state_after_tts
        self._desired_state_after_tts = AppState.LISTENING  # Reset for next time

        # Handle pending transcription that completed during TTS
        # This happens when: user speaks (TRANSCRIBING) → user switches agent (TTS) → transcription completes
        # In this case state is TRANSCRIBING, not PLAYING, so we need to handle it explicitly
        had_pending = self._pending_transcription is not None
        if self._pending_transcription:
            self._pending_transcription = None

        current = self._state_manager.state

        # Transition from PLAYING or TRANSCRIBING (if transcription was deferred)
        if current == AppState.PLAYING or (had_pending and current == AppState.TRANSCRIBING):
            old_state = current
            self._state_manager.transition(target_state, force=True)
            if self._on_state_change:
                self._on_state_change(old_state, target_state, "tts_complete")

        # Process any queued audio now that we're listening again
        if target_state == AppState.LISTENING and self._engine:
            self._engine._process_queued_audio()

    def _handle_hotkey_toggle(self, event: HotkeyToggleEvent) -> None:
        """User wants to toggle listening."""
        current = self._state_manager.state

        if current == AppState.OFF:
            # OFF → LISTENING
            old_state = current
            if self._state_manager.try_transition(AppState.LISTENING):
                if self._on_state_change:
                    self._on_state_change(old_state, AppState.LISTENING, "hotkey_toggle")
                # Sync LLM processor
                if self._engine and self._engine._llm_processor:
                    self._engine._llm_processor.set_listening(True)
        elif self.tts_in_progress:
            # TTS is playing - record user intent for later
            self._desired_state_after_tts = AppState.OFF
        else:
            # Any active state → OFF
            old_state: AppState = current
            if self._state_manager.try_transition(AppState.OFF):
                # Clear buffered audio
                if self._engine:
                    self._engine._discard_current_internal()
                if self._on_state_change:
                    self._on_state_change(old_state, AppState.OFF, "hotkey_toggle")
                # Sync LLM processor
                if self._engine and self._engine._llm_processor:
                    self._engine._llm_processor.set_listening(False)

    def _handle_hotkey_double_tap(self, event: HotkeyDoubleTapEvent) -> None:
        """User double-tapped hotkey to switch mode."""
        if self._engine:
            self._engine._switch_processing_mode_internal()
            if self._on_mode_change:
                self._on_mode_change()

    def _handle_agent_switch(self, event: AgentSwitchEvent) -> None:
        """User wants to switch agent."""
        if not self._engine or not self._engine.agents:
            return

        # Flush VAD to send buffered audio to CURRENT agent before switching
        if self._engine._audio_manager:
            self._engine._audio_manager.flush_vad()

        # Determine new agent
        if event.agent_name:
            # Switch by name
            success = self._engine._switch_to_agent_by_name_internal(event.agent_name)
            if not success:
                return
        elif event.agent_index is not None:
            # Switch by index (1-based)
            success = self._engine._switch_to_agent_by_index_internal(event.agent_index)
            if not success:
                return
        else:
            # Switch by direction
            self._engine._switch_agent_internal(event.direction)

    def _handle_set_listening(self, event: SetListeningEvent) -> None:
        """API request to set listening on/off."""
        current = self._state_manager.state

        if event.on and current == AppState.OFF:
            old_state = current
            if self._state_manager.try_transition(AppState.LISTENING):
                if self._on_state_change:
                    self._on_state_change(old_state, AppState.LISTENING, "set_listening")
                if self._engine and self._engine._llm_processor:
                    self._engine._llm_processor.set_listening(True)
        elif not event.on and current == AppState.LISTENING:
            old_state: AppState = current
            if self._state_manager.try_transition(AppState.OFF):
                if self._on_state_change:
                    self._on_state_change(old_state, AppState.OFF, "set_listening")
                if self._engine and self._engine._llm_processor:
                    self._engine._llm_processor.set_listening(False)

    def _handle_discard_current(self, event: DiscardCurrentEvent) -> None:
        """User wants to discard current recording."""
        if self._engine:
            self._engine._discard_current_internal()

        if self._state_manager.state == AppState.RECORDING:
            old_state = AppState.RECORDING
            self._state_manager.transition(AppState.LISTENING, force=True)
            if self._on_state_change:
                self._on_state_change(old_state, AppState.LISTENING, "discard")
