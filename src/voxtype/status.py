"""Shared display state resolution from engine status.

Both tray app and agent mux parse engine status to determine what to show.
This module provides a single source of truth for that logic.
"""

from __future__ import annotations

# Engine states that mean "actively processing audio"
_ACTIVE_ENGINE_STATES = frozenset(
    {"listening", "recording", "transcribing", "playing"}
)


def resolve_display_state(
    platform: dict, agent_id: str | None = None
) -> tuple[str, str]:
    """Resolve display state from engine platform status dict.

    Args:
        platform: The ``platform`` dict from engine ``/status`` response.
        agent_id: If provided, resolve per-agent state (active/standby).
                  If ``None``, resolve engine-level state.

    Returns:
        ``(state, style)`` tuple:

        - **state**: ``"loading"`` | ``"listening"`` | ``"idle"`` | ``"standby"``
        - **style**: ``"ok"`` (green) | ``"dim"`` (yellow) | ``"warn"`` (red/orange)
    """
    loading = platform.get("loading", {})
    if loading.get("active", False):
        return ("loading", "warn")

    engine_state = platform.get("state", "idle")

    if agent_id is not None:
        current = platform.get("output", {}).get("current_agent")
        is_active = current == agent_id

        if is_active and engine_state in _ACTIVE_ENGINE_STATES:
            return ("listening", "ok")
        elif is_active:
            return ("idle", "dim")
        else:
            return ("standby", "warn")
    else:
        if engine_state in _ACTIVE_ENGINE_STATES:
            return ("listening", "ok")
        else:
            return ("idle", "dim")
