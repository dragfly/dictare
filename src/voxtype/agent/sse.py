"""SSE Agent - delivers OpenVIP messages via the HTTP server's SSE queue."""

from __future__ import annotations

from typing import TYPE_CHECKING

from voxtype.agent.base import BaseAgent, OpenVIPMessage

if TYPE_CHECKING:
    from voxtype.core.http_server import OpenVIPServer

class SSEAgent(BaseAgent):
    """Agent that delivers messages via the HTTP server's SSE queue.

    When an SSE client connects to GET /agents/{agent_id}/messages,
    the server creates an asyncio.Queue for that agent. This agent
    implementation puts messages into that queue via the server's
    thread-safe put_message() method.
    """

    def __init__(self, agent_id: str, server: OpenVIPServer) -> None:
        super().__init__(agent_id)
        self._server = server

    def send(self, message: OpenVIPMessage) -> bool:
        """Send message via the server's SSE queue.

        Args:
            message: OpenVIP message dict.

        Returns:
            True if message was queued, False if agent not connected.
        """
        return self._server.put_message(self._id, message)
