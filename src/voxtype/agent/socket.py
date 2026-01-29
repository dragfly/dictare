"""Socket agent - sends messages via Unix socket.

This agent sends OpenVIP messages to a local process listening
on a Unix domain socket (e.g., Claude Code, Vim plugin).
"""

from __future__ import annotations

import json
import logging
import socket
from collections.abc import Callable
from pathlib import Path

from voxtype.agent.base import BaseAgent, OpenVIPMessage
from voxtype.utils.platform import get_socket_dir

logger = logging.getLogger(__name__)

def get_socket_path(agent_id: str) -> Path:
    """Get Unix socket path for an agent.

    Args:
        agent_id: Agent identifier.

    Returns:
        Path to socket file in the platform-appropriate runtime directory.
    """
    return get_socket_dir() / f"{agent_id}.sock"

class SocketAgent(BaseAgent):
    """Agent that sends messages via Unix domain socket.

    Messages are sent synchronously - each send() call opens a connection,
    sends the message, and closes. This is simple and reliable.

    Supports failure callback for auto-deregistration when socket is dead.
    """

    def __init__(
        self,
        agent_id: str,
        on_failure: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize socket agent.

        Args:
            agent_id: Agent identifier (socket filename without .sock).
            on_failure: Optional callback called with agent_id when send fails.
                       Use this to auto-deregister dead agents.
        """
        super().__init__(agent_id)
        self.socket_path = get_socket_path(agent_id)
        self._on_failure = on_failure

    def is_available(self) -> bool:
        """Check if the agent socket file exists."""
        return self.socket_path.exists()

    def is_alive(self) -> bool:
        """Check if the agent socket has an active listener.

        Attempts to connect to the socket. If connection succeeds,
        there's a listener. If ECONNREFUSED, the socket is stale.

        Returns:
            True if socket has active listener, False otherwise.
        """
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                sock.connect(str(self.socket_path))
            return True
        except ConnectionRefusedError:
            # Socket exists but no listener (stale)
            return False
        except (FileNotFoundError, OSError):
            # Socket doesn't exist or other error
            return False

    def send(self, message: OpenVIPMessage) -> bool:
        """Send an OpenVIP message via socket.

        If send fails and on_failure callback is set, it will be called
        with this agent's ID for auto-deregistration.

        Args:
            message: OpenVIP message dict to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(1.0)
                sock.connect(str(self.socket_path))
                data = json.dumps(message, ensure_ascii=False) + "\n"
                sock.sendall(data.encode("utf-8"))
            return True
        except (OSError, ConnectionRefusedError) as e:
            logger.debug(f"Failed to send to {self._id}: {e}")
            # Notify failure for auto-deregistration
            if self._on_failure:
                self._on_failure(self._id)
            return False

    def __repr__(self) -> str:
        return f"SocketAgent(id={self._id!r}, socket={self.socket_path})"
