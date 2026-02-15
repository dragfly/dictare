"""Observer callbacks for VoxtypeEngine.

EngineEvents is the observer interface for UI integration (audio feedback,
status display). The engine calls _emit("on_xxx", ...) which dispatches
to the registered EngineEvents subclass via reflection.

Only AppController implements callbacks (on_state_change, on_agent_change).
Daemon mode passes events=None — SSE handles everything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxtype.core.fsm import AppState

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

class EngineEvents:
    """Base class for engine event callbacks.

    Subclass and override only the methods you need.
    All methods have default no-op implementations.
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
        pass

    def on_transcription(self, result: TranscriptionResult) -> None:
        """Called when transcription completes.

        Args:
            result: Transcription result with text and timing info.
        """
        pass

    def on_injection(self, result: InjectionResult) -> None:
        """Called when text injection completes.

        Args:
            result: Injection result with success status.
        """
        pass

    def on_agent_change(self, agent_name: str, index: int) -> None:
        """Called when the active agent changes.

        Args:
            agent_name: Name of the new active agent.
            index: Index of the new active agent (0-based).
        """
        pass

    def on_agents_changed(self, agents: list[str]) -> None:
        """Called when the agents list changes (auto-discovery).

        Args:
            agents: Updated list of agent IDs.
        """
        pass

    def on_error(self, message: str, context: str) -> None:
        """Called when an error occurs.

        Args:
            message: Error message.
            context: Context where the error occurred.
        """
        pass

    def on_engine_ready(self) -> None:
        """Called when engine initialization is complete (STT, VAD loaded)."""
        pass

    def on_partial_transcription(self, text: str) -> None:
        """Called during realtime transcription with partial text.

        Args:
            text: Partial transcription text so far.
        """
        pass

    def on_recording_start(self) -> None:
        """Called when recording starts (VAD detected speech)."""
        pass

    def on_recording_end(self, duration_ms: float) -> None:
        """Called when recording ends.

        Args:
            duration_ms: Recording duration in milliseconds.
        """
        pass

    def on_max_duration_reached(self) -> None:
        """Called when max speech duration is reached and audio is being sent."""
        pass

    def on_vad_loading(self) -> None:
        """Called when VAD model starts loading."""
        pass

    def on_device_reconnect_attempt(self, attempt: int) -> None:
        """Called when audio device reconnection is attempted.

        Args:
            attempt: Attempt number (1-5).
        """
        pass

    def on_device_reconnect_success(self, device_name: str | None) -> None:
        """Called when audio device reconnection succeeds.

        Args:
            device_name: Name of the reconnected device, or None if unknown.
        """
        pass
