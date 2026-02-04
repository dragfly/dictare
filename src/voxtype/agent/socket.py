"""Socket agent - sends messages via Unix socket.

This agent sends OpenVIP messages to a local process listening
on a Unix domain socket (e.g., Claude Code, Vim plugin).

Uses a PERSISTENT connection - connects once, sends many messages.
Connection only closes when agent dies or engine stops.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
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

    Uses a PERSISTENT connection:
    - connect() called once when engine discovers the agent
    - send() reuses the same connection for all messages
    - disconnect() called when agent dies or engine stops

    This avoids the backlog problem of opening/closing per message.
    """

    def __init__(
        self,
        agent_id: str,
        on_failure: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize socket agent.

        Args:
            agent_id: Agent identifier (socket filename without .sock).
            on_failure: Optional callback called with agent_id when connection fails.
        """
        super().__init__(agent_id)
        self.socket_path = get_socket_path(agent_id)
        self._on_failure = on_failure
        self._socket: socket.socket | None = None
        self._lock = threading.Lock()  # Thread-safe send

    def is_available(self) -> bool:
        """Check if the agent socket file exists."""
        return self.socket_path.exists()

    def is_alive(self) -> bool:
        """Check if connected to the agent."""
        return self._socket is not None

    def connect(self) -> bool:
        """Establish persistent connection to agent.

        Called once when engine discovers/registers the agent.

        Returns:
            True if connected successfully, False otherwise.
        """
        if self._socket is not None:
            return True  # Already connected

        try:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.settimeout(5.0)  # 5s timeout for connect
            self._socket.connect(str(self.socket_path))
            # Once connected, no timeout for sends (blocking is fine)
            self._socket.settimeout(None)
            logger.debug(f"Connected to agent {self._id}")
            return True
        except (OSError, ConnectionRefusedError) as e:
            logger.warning(f"Failed to connect to agent {self._id}: {e}")
            self._socket = None
            return False

    def disconnect(self) -> None:
        """Close the persistent connection.

        Called when agent dies or engine stops.
        """
        with self._lock:
            if self._socket is not None:
                try:
                    self._socket.close()
                except OSError:
                    pass
                self._socket = None
                logger.debug(f"Disconnected from agent {self._id}")

    def send(self, message: OpenVIPMessage) -> bool:
        """Send an OpenVIP message via the persistent connection.

        Thread-safe - multiple threads can call send() concurrently.

        Args:
            message: OpenVIP message dict to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        data = json.dumps(message, ensure_ascii=False) + "\n"
        data_bytes = data.encode("utf-8")

        with self._lock:
            # Auto-connect if not connected
            if self._socket is None:
                if not self.connect():
                    if self._on_failure:
                        self._on_failure(self._id)
                    return False

            sock = self._socket
            if sock is None:
                return False

            try:
                sock.sendall(data_bytes)
                return True
            except (BrokenPipeError, OSError) as e:
                # Connection lost - cleanup and notify
                logger.warning(f"Connection to {self._id} lost: {e}")
                try:
                    sock.close()
                except OSError:
                    pass
                self._socket = None

                if self._on_failure:
                    self._on_failure(self._id)
                return False

    def __repr__(self) -> str:
        connected = "connected" if self._socket else "disconnected"
        return f"SocketAgent(id={self._id!r}, {connected})"
