"""Tests for SSEAgent message delivery."""

from __future__ import annotations

import threading

from voxtype.agent.base import BaseAgent, OpenVIPMessage
from voxtype.agent.sse import SSEAgent


class MockServer:
    """Mock OpenVIPServer for testing SSEAgent."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []
        self._return_value = True

    def put_message(self, agent_id: str, message: dict) -> bool:
        self.messages.append((agent_id, message))
        return self._return_value


class TestSSEAgentInit:
    """Test SSEAgent initialization."""

    def test_id_property(self) -> None:
        """Agent exposes its ID."""
        server = MockServer()
        agent = SSEAgent("claude", server)
        assert agent.id == "claude"

    def test_is_base_agent(self) -> None:
        """SSEAgent is a BaseAgent subclass."""
        server = MockServer()
        agent = SSEAgent("test", server)
        assert isinstance(agent, BaseAgent)

    def test_repr(self) -> None:
        """Agent has a useful repr."""
        server = MockServer()
        agent = SSEAgent("my-agent", server)
        assert "SSEAgent" in repr(agent)
        assert "my-agent" in repr(agent)


class TestSSEAgentSend:
    """Test SSEAgent.send() method."""

    def test_send_delegates_to_server(self) -> None:
        """send() calls server.put_message() with correct args."""
        server = MockServer()
        agent = SSEAgent("claude", server)

        message: OpenVIPMessage = {
            "openvip": "1.0",
            "type": "message",
            "text": "hello world",
        }
        result = agent.send(message)

        assert result is True
        assert len(server.messages) == 1
        assert server.messages[0] == ("claude", message)

    def test_send_returns_false_when_not_connected(self) -> None:
        """send() returns False when server can't deliver."""
        server = MockServer()
        server._return_value = False
        agent = SSEAgent("ghost", server)

        result = agent.send({"text": "hello"})
        assert result is False

    def test_send_multiple_messages(self) -> None:
        """Multiple messages are delivered in order."""
        server = MockServer()
        agent = SSEAgent("test", server)

        for i in range(5):
            agent.send({"text": f"msg-{i}"})

        assert len(server.messages) == 5
        for i in range(5):
            assert server.messages[i][1]["text"] == f"msg-{i}"

    def test_send_preserves_message_content(self) -> None:
        """Message content is passed through unchanged."""
        server = MockServer()
        agent = SSEAgent("test", server)

        msg: OpenVIPMessage = {
            "openvip": "1.0",
            "type": "message",
            "id": "abc-123",
            "timestamp": "2026-01-01T00:00:00Z",
            "text": "hello",
            "x_submit": True,
            "language": "en",
        }
        agent.send(msg)

        delivered = server.messages[0][1]
        assert delivered is msg  # Same dict reference


class TestSSEAgentThreadSafety:
    """Test SSEAgent thread safety."""

    def test_concurrent_sends(self) -> None:
        """Multiple threads can send concurrently without errors."""
        server = MockServer()
        agent = SSEAgent("test", server)
        errors: list[Exception] = []

        def send_many(thread_id: int) -> None:
            try:
                for i in range(50):
                    agent.send({"text": f"t{thread_id}-{i}"})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=send_many, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(server.messages) == 250  # 5 threads * 50 messages
