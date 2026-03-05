"""Shared display state resolution from engine status.

Both tray app and agent mux parse engine status to determine what to show.
This module provides a single source of truth for that logic.
"""

from __future__ import annotations

# Engine states that mean "actively processing audio"
_ACTIVE_ENGINE_STATES = frozenset(
    {"listening", "recording", "transcribing", "playing", "muted"}
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

        - **state**: ``"loading"`` | ``"listening"`` | ``"muted"`` | ``"off"`` | ``"standby"``
        - **style**: ``"ok"`` (green) | ``"dim"`` (gray) | ``"warn"`` (orange)
    """
    loading = platform.get("loading", {})
    if loading.get("active", False):
        return ("loading", "warn")

    engine_state = platform.get("state", "off")

    if agent_id is not None:
        current = platform.get("output", {}).get("current_agent")
        is_active = current == agent_id

        if is_active and engine_state == "muted":
            return ("muted", "dim")
        elif is_active and engine_state in _ACTIVE_ENGINE_STATES:
            return ("listening", "ok")
        elif is_active:
            return ("off", "dim")
        elif engine_state in _ACTIVE_ENGINE_STATES:
            return ("standby", "warn")
        else:
            return ("standby", "dim")
    else:
        if engine_state == "muted":
            return ("muted", "dim")
        elif engine_state in _ACTIVE_ENGINE_STATES:
            return ("listening", "ok")
        else:
            return ("off", "dim")
