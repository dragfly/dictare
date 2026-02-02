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
    Uses consecutive failure tracking to avoid spurious deregistration.
    """

    # Number of consecutive failures before triggering on_failure callback
    FAILURE_THRESHOLD = 3

    def __init__(
        self,
        agent_id: str,
        on_failure: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize socket agent.

        Args:
            agent_id: Agent identifier (socket filename without .sock).
            on_failure: Optional callback called with agent_id when send fails
                       FAILURE_THRESHOLD consecutive times.
        """
        super().__init__(agent_id)
        self.socket_path = get_socket_path(agent_id)
        self._on_failure = on_failure
        self._consecutive_failures = 0

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
        """Send an OpenVIP message via socket with retry.

        Retries up to 2 times with increasing timeout on transient failures.
        Only triggers on_failure callback after FAILURE_THRESHOLD consecutive
        failures across multiple send() calls.

        Args:
            message: OpenVIP message dict to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        data = json.dumps(message, ensure_ascii=False) + "\n"
        data_bytes = data.encode("utf-8")

        # Retry with increasing timeouts: 1.0s, 2.0s, 3.0s
        for attempt in range(3):
            timeout = 1.0 + attempt
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(timeout)
                    sock.connect(str(self.socket_path))
                    sock.sendall(data_bytes)
                # Success - reset failure counter
                self._consecutive_failures = 0
                return True
            except (TimeoutError, BlockingIOError):
                # Transient - retry with longer timeout
                logger.debug(f"Timeout sending to {self._id}, attempt {attempt + 1}/3")
                continue
            except (OSError, ConnectionRefusedError) as e:
                # Connection error - don't retry, but track failure
                logger.debug(f"Failed to send to {self._id}: {e}")
                break

        # All attempts failed
        self._consecutive_failures += 1
        logger.debug(
            f"Send to {self._id} failed, consecutive failures: {self._consecutive_failures}"
        )

        # Only trigger deregistration after multiple consecutive failures
        if self._consecutive_failures >= self.FAILURE_THRESHOLD and self._on_failure:
            logger.warning(
                f"Agent {self._id} failed {self.FAILURE_THRESHOLD} times, triggering deregistration"
            )
            self._on_failure(self._id)

        return False

    def __repr__(self) -> str:
        return f"SocketAgent(id={self._id!r}, socket={self.socket_path})"
