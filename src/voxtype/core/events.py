"""Event types and protocol for VoxtypeEngine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from voxtype.core.state import AppState, ProcessingMode


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
