"""Event types and protocol for VoxtypeEngine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from voxtype.core.state import AppState, ProcessingMode

# =============================================================================
# State Events (for Event Queue Architecture)
# =============================================================================

@dataclass(frozen=True)
class StateEvent:
    """Base event with timestamp and source.

    All events are immutable (frozen=True) to ensure thread-safety.
    Events are processed FIFO - no priority.
    """

    timestamp: float = field(default_factory=time.time)
    source: str = ""  # "vad", "stt", "tts", "hotkey", "api", etc.

@dataclass(frozen=True)
class SpeechStartEvent(StateEvent):
    """VAD detected speech start."""

    pass

@dataclass(frozen=True)
class SpeechEndEvent(StateEvent):
    """VAD detected speech end.

    Captures audio_data and injector at event creation time,
    ensuring they go to the correct agent even if agent switches later.
    """

    audio_data: Any = None
    injector: Any = None  # Captured at event creation time

@dataclass(frozen=True)
class TranscriptionCompleteEvent(StateEvent):
    """STT finished transcribing."""

    text: str = ""
    injector: Any = None  # The injector to use for injection

@dataclass(frozen=True)
class TTSStartEvent(StateEvent):
    """TTS playback starting.

    Each TTS start increments a counter. The tts_id is assigned by the controller
    when the event is processed, not when it's created.
    """

    text: str = ""

@dataclass(frozen=True)
class TTSCompleteEvent(StateEvent):
    """TTS playback finished.

    The tts_id must match the ID assigned when TTSStartEvent was processed.
    If multiple TTS are playing concurrently, only the completion of the
    LAST started TTS will trigger state transition back to LISTENING.
    """

    tts_id: int = 0  # Must match the ID from TTSStartEvent

@dataclass(frozen=True)
class HotkeyToggleEvent(StateEvent):
    """User pressed hotkey to toggle listening."""

    pass

@dataclass(frozen=True)
class HotkeyDoubleTapEvent(StateEvent):
    """User double-tapped hotkey to switch mode."""

    pass

@dataclass(frozen=True)
class AgentSwitchEvent(StateEvent):
    """User wants to switch agent."""

    direction: int = 1  # +1 next, -1 prev
    agent_name: str | None = None  # If switching by name
    agent_index: int | None = None  # If switching by index (1-based)

@dataclass(frozen=True)
class SetListeningEvent(StateEvent):
    """API request to set listening on/off."""

    on: bool = True

@dataclass(frozen=True)
class DiscardCurrentEvent(StateEvent):
    """User wants to discard current recording."""

    pass

# =============================================================================
# UI Event Results
# =============================================================================

@dataclass
class TranscriptionResult:
    """Result of a transcription operation."""

    text: str
    audio_duration_seconds: float
    transcription_seconds: float

@dataclass
class InjectionResult:
    """Result of a text injection operation."""

    text: str
    success: bool
    method: str
    error: str | None = None  # Error message if success=False

@runtime_checkable
class EngineEvents(Protocol):
    """Protocol for engine event callbacks.

    Implement this protocol to receive events from VoxtypeEngine.
    All methods are optional - only implement what you need.
    """

    def on_state_change(
        self, old: AppState, new: AppState, trigger: str
    ) -> None:
        """Called when the engine state changes.

        Args:
            old: Previous state.
            new: New state.
            trigger: What triggered the change (e.g., "hotkey_toggle", "voice_command").
        """
        ...

    def on_transcription(self, result: TranscriptionResult) -> None:
        """Called when transcription completes.

        Args:
            result: Transcription result with text and timing info.
        """
        ...

    def on_injection(self, result: InjectionResult) -> None:
        """Called when text injection completes.

        Args:
            result: Injection result with success status.
        """
        ...

    def on_mode_change(self, mode: ProcessingMode) -> None:
        """Called when processing mode changes.

        Args:
            mode: New processing mode (TRANSCRIPTION or COMMAND).
        """
        ...

    def on_agent_change(self, agent_name: str, index: int) -> None:
        """Called when the active agent changes.

        Args:
            agent_name: Name of the new active agent.
            index: Index of the new active agent (0-based).
        """
        ...

    def on_error(self, message: str, context: str) -> None:
        """Called when an error occurs.

        Args:
            message: Error message.
            context: Context where the error occurred.
        """
        ...

    def on_partial_transcription(self, text: str) -> None:
        """Called during realtime transcription with partial text.

        Args:
            text: Partial transcription text so far.
        """
        ...

    def on_recording_start(self) -> None:
        """Called when recording starts (VAD detected speech)."""
        ...

    def on_recording_end(self, duration_ms: float) -> None:
        """Called when recording ends.

        Args:
            duration_ms: Recording duration in milliseconds.
        """
        ...

    def on_max_duration_reached(self) -> None:
        """Called when max speech duration is reached and audio is being sent."""
        ...

    def on_vad_loading(self) -> None:
        """Called when VAD model starts loading."""
        ...

    def on_device_reconnect_attempt(self, attempt: int) -> None:
        """Called when audio device reconnection is attempted.

        Args:
            attempt: Attempt number (1-5).
        """
        ...

    def on_device_reconnect_success(self, device_name: str | None) -> None:
        """Called when audio device reconnection succeeds.

        Args:
            device_name: Name of the reconnected device, or None if unknown.
        """
        ...
