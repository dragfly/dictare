"""Agent registration mechanisms.

Provides different ways to register agents with the engine:
- ManualAgentRegistrar: Register agents from CLI args (deterministic)
- AutoDiscoveryRegistrar: Watch socket directory and register dynamically
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from voxtype.agent.base import Agent

class AgentRegistry(Protocol):
    """Protocol for objects that can register/unregister agents."""

    def register_agent(self, agent: Agent) -> bool:
        """Register an agent."""
        ...

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent."""
        ...

class AgentRegistrar(ABC):
    """Base class for agent registration mechanisms.

    Subclasses implement different discovery strategies but all
    use the same engine API to register/unregister agents.
    """

    def __init__(self, registry: AgentRegistry) -> None:
        """Initialize with a registry (typically the engine).

        Args:
            registry: Object with register_agent/unregister_agent methods.
        """
        self._registry = registry

    @abstractmethod
    def start(self) -> None:
        """Start the registrar (discover and register agents)."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the registrar (cleanup)."""
        ...

class ManualAgentRegistrar(AgentRegistrar):
    """Register agents from a static list (CLI args).

    Simple, deterministic, reliable. Agents are registered once
    at startup and never change.

    Auto-deregisters agents when they fail to respond.
    """

    def __init__(self, registry: AgentRegistry, agent_ids: list[str]) -> None:
        """Initialize with a list of agent IDs.

        Args:
            registry: Object with register_agent/unregister_agent methods.
            agent_ids: List of agent IDs to register.
        """
        super().__init__(registry)
        self._agent_ids = agent_ids

    def start(self) -> None:
        """Register all agents from the list (as SocketAgents)."""
        from voxtype.agent.socket import SocketAgent

        def on_agent_failure(agent_id: str) -> None:
            """Auto-deregister agent when it fails."""
            self._registry.unregister_agent(agent_id)

        for agent_id in self._agent_ids:
            agent = SocketAgent(agent_id, on_failure=on_agent_failure)
            self._registry.register_agent(agent)

    def stop(self) -> None:
        """Nothing to clean up for manual registration."""
        pass

class AutoDiscoveryRegistrar(AgentRegistrar):
    """Register agents by watching the socket directory.

    Supports pluggable monitoring strategies:
    - "polling": Reliable, checks directory every N seconds (default)
    - "watchdog": Fast, uses filesystem events (may miss events)
    """

    def __init__(
        self,
        registry: AgentRegistry,
        monitor_type: str = "polling",
        poll_interval: float = 1.0,
    ) -> None:
        """Initialize auto-discovery.

        Args:
            registry: Object with register_agent/unregister_agent methods.
            monitor_type: "polling" (reliable) or "watchdog" (fast).
            poll_interval: Seconds between polls (only for polling monitor).
        """
        super().__init__(registry)
        self._monitor_type = monitor_type
        self._poll_interval = poll_interval
        self._monitor: Any = None

    def start(self) -> None:
        """Start monitoring for agents and register existing ones."""
        from voxtype.agent.monitor import create_monitor
        from voxtype.agent.socket import SocketAgent

        def on_agent_failure(agent_id: str) -> None:
            """Auto-deregister agent when it fails."""
            self._registry.unregister_agent(agent_id)

        def on_agent_added(discovered_agent: Any) -> None:
            """Create SocketAgent and register it."""
            agent = SocketAgent(discovered_agent.id, on_failure=on_agent_failure)
            self._registry.register_agent(agent)

        def on_agent_removed(discovered_agent: Any) -> None:
            """Unregister agent by ID."""
            self._registry.unregister_agent(discovered_agent.id)

        self._monitor = create_monitor(
            monitor_type=self._monitor_type,
            on_agent_added=on_agent_added,
            on_agent_removed=on_agent_removed,
            poll_interval=self._poll_interval,
        )
        self._monitor.start()

        # Register agents discovered at startup
        for agent_id in self._monitor.agent_ids:
            agent = SocketAgent(agent_id, on_failure=on_agent_failure)
            self._registry.register_agent(agent)

    def stop(self) -> None:
        """Stop monitoring."""
        if self._monitor:
            self._monitor.stop()
            self._monitor = None
