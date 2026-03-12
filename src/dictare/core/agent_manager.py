"""Agent registration, switching, and lifecycle management.

Extracted from DictareEngine to reduce god-object complexity.
The engine delegates all agent-related state and operations here.
"""

from __future__ import annotations

import logging
import time as _time
from collections.abc import Callable
from typing import TYPE_CHECKING

from dictare.core.bus import bus

if TYPE_CHECKING:
    from dictare.agent.base import Agent

logger = logging.getLogger(__name__)

class AgentManager:
    """Manages agent registration, switching, and output mode.

    Owns all agent-related state:
    - Agent registry (_agents dict, _agent_order list)
    - Current agent tracking (_current_agent_id, _last_sse_agent_id)
    - Grace period for preferred agent reconnection

    Side effects (UI events, status push) are dispatched via callbacks
    set by the engine after construction.
    """

    KEYBOARD_AGENT_ID = "__keyboard__"
    TTS_AGENT_ID = "__tts__"
    RESERVED_AGENT_IDS = frozenset({KEYBOARD_AGENT_ID, TTS_AGENT_ID})

    def __init__(self, *, initial_agent_id: str | None = None) -> None:
        self._agents: dict[str, Agent] = {}
        self._agent_order: list[str] = []
        self._current_agent_id: str | None = initial_agent_id
        self._last_sse_agent_id: str | None = None
        self._preferred_agent_deadline: float | None = None

        # Callbacks — set by engine after construction
        self._on_notify: Callable[[], None] | None = None
        self._on_agent_change: Callable[[str, int], None] | None = None
        self._on_speak: Callable[[str], None] | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def agent_mode(self) -> bool:
        """True when outputting to agents, False when keyboard."""
        return self._current_agent_id != self.KEYBOARD_AGENT_ID

    @property
    def agents(self) -> list[str]:
        """All registered agent IDs (including internal)."""
        return self._agent_order.copy()

    @property
    def visible_agents(self) -> list[str]:
        """User-visible agent IDs (excludes internal agents)."""
        return [a for a in self._agent_order if a not in self.RESERVED_AGENT_IDS]

    @property
    def current_agent(self) -> str | None:
        """ID of the current agent, or None."""
        return self._current_agent_id

    @property
    def visible_current_agent(self) -> str | None:
        """Current agent ID, or None if it's an internal agent."""
        if self._current_agent_id in self.RESERVED_AGENT_IDS:
            return None
        return self._current_agent_id

    @property
    def current_agent_index(self) -> int:
        """Index of the current agent (0-based)."""
        if self._current_agent_id and self._current_agent_id in self._agent_order:
            return self._agent_order.index(self._current_agent_id)
        return 0

    def get_current(self) -> Agent | None:
        """Get the current Agent instance."""
        if self._current_agent_id:
            return self._agents.get(self._current_agent_id)
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _notify(self) -> None:
        """Push status update via engine callback."""
        if self._on_notify:
            self._on_notify()

    def _set_current(self, agent_id: str, idx: int = 0) -> None:
        """Set current agent, emit event, and push status update."""
        if agent_id == self._current_agent_id:
            logger.debug("_set_current_agent: already %s, skipping", agent_id)
            return
        logger.info("_set_current_agent: %s (idx=%d)", agent_id, idx)
        self._current_agent_id = agent_id
        if self._on_agent_change:
            self._on_agent_change(agent_id, idx)
        self._notify()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, agent: Agent) -> bool:
        """Register an agent.

        Args:
            agent: The Agent instance to register.

        Returns:
            True if agent was added, False if already registered.
        """
        if agent.id in self._agents:
            return False

        self._agents[agent.id] = agent
        self._agent_order.append(agent.id)

        # Activate this agent if:
        # 1. It's the saved preferred agent from last session, OR
        # 2. No current agent OR current is internal in agents mode
        if agent.id not in self.RESERVED_AGENT_IDS:
            if self._last_sse_agent_id and agent.id == self._last_sse_agent_id:
                self._current_agent_id = agent.id
                logger.info(
                    "register_agent(%s): activated (matches preferred agent from saved state)",
                    agent.id,
                )
            elif self._current_agent_id is None or (
                self.agent_mode and self._current_agent_id in self.RESERVED_AGENT_IDS
            ):
                self._current_agent_id = agent.id
                logger.info(
                    "register_agent(%s): activated as first real agent "
                    "(current_agent was %r, agent_mode=%r)",
                    agent.id, self._current_agent_id, self.agent_mode,
                )
            else:
                logger.info(
                    "register_agent(%s): registered but not activated "
                    "(current_agent=%r, preferred=%r)",
                    agent.id, self._current_agent_id, self._last_sse_agent_id,
                )
        else:
            logger.info("register_agent(%s): reserved agent registered", agent.id)

        bus.publish("agent.registered", agent_id=agent.id)
        self._notify()
        return True

    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent by ID.

        Args:
            agent_id: The agent identifier to remove.

        Returns:
            True if agent was removed, False if not found.
        """
        if agent_id not in self._agents:
            return False

        was_current = self._current_agent_id == agent_id

        del self._agents[agent_id]
        self._agent_order = [a for a in self._agent_order if a != agent_id]

        if was_current:
            visible = self.visible_agents
            if visible:
                self._set_current(visible[0])
            else:
                self._current_agent_id = None

        bus.publish("agent.unregistered", agent_id=agent_id)
        self._notify()
        return True

    # ------------------------------------------------------------------
    # Switching
    # ------------------------------------------------------------------

    def switch_by_direction(self, direction: int) -> None:
        """Switch to next/previous agent (circular).

        Args:
            direction: +1 for next, -1 for previous.
        """
        if not self._agent_order:
            return

        current_idx = 0
        if self._current_agent_id and self._current_agent_id in self._agent_order:
            current_idx = self._agent_order.index(self._current_agent_id)

        new_idx = (current_idx + direction) % len(self._agent_order)
        new_agent_id = self._agent_order[new_idx]

        if new_agent_id in self._agents:
            self._set_current(new_agent_id, new_idx)

    def switch_by_name(self, name: str) -> bool:
        """Switch to agent by name (exact match, then partial).

        Args:
            name: Agent name to switch to.

        Returns:
            True if switched, False if not found.
        """
        if not self._agent_order:
            return False

        name_lower = name.lower()

        def try_switch(agent_id: str, idx: int) -> bool:
            if agent_id not in self._agents:
                return False
            self._set_current(agent_id, idx)
            return True

        # Exact match first
        for i, agent_id in enumerate(self._agent_order):
            if agent_id.lower() == name_lower:
                return try_switch(agent_id, i)

        # Partial match
        for i, agent_id in enumerate(self._agent_order):
            if name_lower in agent_id.lower():
                return try_switch(agent_id, i)

        return False

    def switch_by_index(self, index: int) -> bool:
        """Switch to agent by 1-based index.

        Args:
            index: 1-based agent index.

        Returns:
            True if switched, False if out of range.
        """
        if not self._agent_order:
            return False

        idx = index - 1
        if idx < 0 or idx >= len(self._agent_order):
            return False

        agent_id = self._agent_order[idx]
        if agent_id not in self._agents:
            return False

        self._set_current(agent_id, idx)
        return True

    # ------------------------------------------------------------------
    # Output mode
    # ------------------------------------------------------------------

    def set_output_mode(self, mode: str) -> None:
        """Switch output mode (keyboard <-> agents).

        Args:
            mode: "keyboard" or "agents".
        """
        if mode not in ("keyboard", "agents"):
            return

        want_agent_mode = mode == "agents"
        if want_agent_mode == self.agent_mode:
            logger.debug("set_output_mode(%r): already in this mode, no-op", mode)
            return

        logger.info(
            "set_output_mode: %s -> %s (current_agent=%r, last_sse_agent=%r)",
            "agents" if self.agent_mode else "keyboard", mode,
            self._current_agent_id, self._last_sse_agent_id,
        )

        if want_agent_mode:
            restore_id = self._last_sse_agent_id
            real_agents = self.visible_agents
            if restore_id and restore_id in self._agents:
                self._current_agent_id = restore_id
            elif real_agents:
                self._current_agent_id = real_agents[0]
            else:
                self._current_agent_id = None
            if self._on_speak:
                self._on_speak("agent mode")
        else:
            if self._current_agent_id and self._current_agent_id != self.KEYBOARD_AGENT_ID:
                self._last_sse_agent_id = self._current_agent_id
            self._current_agent_id = self.KEYBOARD_AGENT_ID
            if self._on_speak:
                self._on_speak("keyboard mode")

        self._notify()

    # ------------------------------------------------------------------
    # Session restore
    # ------------------------------------------------------------------

    def restore_session(self, saved_agent: str | None, *, grace_seconds: float = 20.0) -> None:
        """Restore agent state from a previous session.

        Args:
            saved_agent: The agent ID that was active when the session ended,
                or KEYBOARD_AGENT_ID for keyboard mode, or None for no-op.
            grace_seconds: How long to wait for the preferred agent to reconnect.
        """
        if not saved_agent:
            return

        if saved_agent == self.KEYBOARD_AGENT_ID:
            self._current_agent_id = self.KEYBOARD_AGENT_ID
            logger.info("restore_session: keyboard mode")
        else:
            self._current_agent_id = None  # agents mode, waiting
            self._last_sse_agent_id = saved_agent
            self._preferred_agent_deadline = _time.monotonic() + grace_seconds
            logger.info("restore_session: waiting for agent %r (%.0fs grace)", saved_agent, grace_seconds)

    # ------------------------------------------------------------------
    # Grace period
    # ------------------------------------------------------------------

    def check_grace_period(self) -> None:
        """Assign first available agent once the preferred-agent grace period expires."""
        if self._preferred_agent_deadline is None:
            return
        if _time.monotonic() < self._preferred_agent_deadline:
            return
        self._preferred_agent_deadline = None
        if self.agent_mode and (
            self._current_agent_id is None
            or self._current_agent_id in self.RESERVED_AGENT_IDS
        ):
            visible = self.visible_agents
            if visible:
                self._current_agent_id = visible[0]
                logger.info(
                    "grace_period_expired: preferred agent never reconnected, "
                    "activating first available agent %r",
                    visible[0],
                )
