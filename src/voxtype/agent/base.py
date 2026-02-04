"""Agent base classes and protocol.

An Agent is a destination for OpenVIP messages. Different agent types
handle different transports:
- KeyboardAgent: simulates keystrokes locally
- SSEAgent: sends via Server-Sent Events (OpenVIP HTTP server)

The engine doesn't know about transports - it just calls agent.send().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

# OpenVIP message type
OpenVIPMessage = dict[str, Any]


@runtime_checkable
class Agent(Protocol):
    """Protocol for message destinations.

    All agents must have an ID and be able to receive messages.
    The transport mechanism is encapsulated in the implementation.
    """

    @property
    def id(self) -> str:
        """Unique identifier for this agent."""
        ...

    def send(self, message: OpenVIPMessage) -> bool:
        """Send an OpenVIP message to this agent.

        Args:
            message: OpenVIP message dict to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        ...


class BaseAgent(ABC):
    """Base class for agent implementations.

    Provides common functionality and enforces the Agent interface.
    Subclasses implement the actual transport mechanism.
    """

    def __init__(self, agent_id: str) -> None:
        """Initialize agent with ID.

        Args:
            agent_id: Unique identifier for this agent.
        """
        self._id = agent_id

    @property
    def id(self) -> str:
        """Unique identifier for this agent."""
        return self._id

    @abstractmethod
    def send(self, message: OpenVIPMessage) -> bool:
        """Send an OpenVIP message to this agent.

        Args:
            message: OpenVIP message dict to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self._id!r})"
