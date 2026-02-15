"""Observer callbacks for VoxtypeEngine.

EngineEvents is the observer interface for UI integration (audio feedback,
status display). The engine calls _emit("on_xxx", ...) which dispatches
to the registered EngineEvents subclass via reflection.

Only AppController implements callbacks (on_state_change, on_agent_change).
Daemon mode passes events=None — SSE handles everything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxtype.core.fsm import AppState

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

    def on_agent_change(self, agent_name: str, index: int) -> None:
        """Called when the active agent changes.

        Args:
            agent_name: Name of the new active agent.
            index: Index of the new active agent (0-based).
        """
        pass
