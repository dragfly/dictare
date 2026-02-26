"""OpenVIP Internal Tests — dictare implementation details.

These tests verify dictare-specific behavior that is NOT part of the OpenVIP
protocol specification. They use mock internals (TestClient, mock engine) and
are automatically skipped when running with --openvip-url.

All tests in this file are marked @pytest.mark.internal.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dictare.core.http_server import OpenVIPServer

# =============================================================================
# Fixtures — TestClient for fast in-process testing
# =============================================================================

@pytest.fixture
def client(server):
    """In-process HTTP client using FastAPI TestClient."""
    yield TestClient(server._app)

# =============================================================================
# Status — engine state reflection
# =============================================================================

@pytest.mark.internal
class TestStatusInternal:
    """Internal: GET /status reflects engine internals."""

    def test_state_reflects_engine(self, client, engine) -> None:
        """Status stt.active reflects engine state."""
        engine._state = "listening"
        data = client.get("/status").json()
        assert data["stt"]["active"] is True

# =============================================================================
# Control — routing and error handling
# =============================================================================

@pytest.mark.internal
class TestControlInternal:
    """Internal: POST /control routing and error handling."""

    def test_engine_shutdown(self, client) -> None:
        """engine.shutdown returns ok."""
        r = client.post("/control", json={"command": "engine.shutdown"})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_stt_start_routed_to_engine(self, client, engine) -> None:
        """stt.start is routed to engine, not controller."""
        client.post("/control", json={"command": "stt.start"})
        assert len(engine._protocol_calls) == 1
        assert engine._protocol_calls[0]["command"] == "stt.start"

    def test_all_protocol_commands_go_to_engine(
        self, client, engine, controller,
    ) -> None:
        """All protocol commands route to engine, none to controller."""
        for cmd in ["stt.start", "stt.stop", "stt.toggle",
                     "engine.shutdown", "ping"]:
            client.post("/control", json={"command": cmd})
        assert len(engine._protocol_calls) == 5
        assert len(controller._calls) == 0

# =============================================================================
# Control — routing between engine and controller
# =============================================================================

@pytest.mark.internal
class TestControlRouting:
    """Internal: POST /control routing between engine and controller."""

    def test_app_command_routed_to_controller(self, client, controller) -> None:
        """Non-protocol commands go to controller."""
        client.post("/control", json={"command": "output.set_mode:agents"})
        assert len(controller._calls) == 1

    def test_app_command_not_routed_to_engine(self, client, engine) -> None:
        """Non-protocol commands do not reach engine."""
        client.post("/control", json={"command": "output.set_agent:claude"})
        assert len(engine._protocol_calls) == 0

    def test_unknown_command_without_controller(self, engine) -> None:
        """Unknown command without controller returns error."""
        server = OpenVIPServer(engine, None, host="127.0.0.1", port=0)
        c = TestClient(server._app)
        r = c.post("/control", json={"command": "foo.bar"})
        assert r.status_code == 200
        assert r.json()["status"] == "error"

    def test_control_engine_error_returns_500(self, client, engine) -> None:
        """Engine exception results in 500."""
        engine.handle_protocol_command = MagicMock(
            side_effect=RuntimeError("boom")
        )
        r = client.post("/control", json={"command": "stt.start"})
        assert r.status_code == 500

# =============================================================================
# Speech — internal behavior
# =============================================================================

@pytest.mark.internal
class TestSpeechInternal:
    """Internal: POST /speech engine interaction."""

    def test_speech_with_language(self, client, engine) -> None:
        """Speech request with language is accepted."""
        r = client.post("/speech", json={
            "openvip": "1.0", "type": "speech", "text": "hello", "language": "en",
        })
        assert r.status_code == 200
        assert engine._speech_calls[-1]["language"] == "en"

    def test_speech_text_forwarded(self, client, engine) -> None:
        """Speech text is forwarded to engine."""
        client.post("/speech", json={
            "openvip": "1.0", "type": "speech", "text": "say this",
        })
        assert engine._speech_calls[-1]["text"] == "say this"

    def test_speech_engine_error_returns_500(self, client, engine) -> None:
        """Engine exception results in 500."""
        engine.handle_speech = MagicMock(side_effect=RuntimeError("TTS fail"))
        r = client.post("/speech", json={
            "openvip": "1.0", "type": "speech", "text": "hello",
        })
        assert r.status_code == 500

# =============================================================================
# PUT Message (thread-safe delivery)
# =============================================================================

@pytest.mark.internal
class TestPutMessage:
    """Internal: Server.put_message() thread-safe delivery."""

    def test_returns_false_for_unconnected_agent(
        self, server: OpenVIPServer,
    ) -> None:
        result = server.put_message("ghost", {"text": "hi"})
        assert result is False

    def test_returns_false_without_event_loop(
        self, server: OpenVIPServer,
    ) -> None:
        """put_message returns False when server event loop not running."""
        with server._agent_queues_lock:
            server._agent_queues["test"] = asyncio.Queue()
        result = server.put_message("test", {"text": "hi"})
        assert result is False

# =============================================================================
# Connected Agents
# =============================================================================

@pytest.mark.internal
class TestConnectedAgents:
    """Internal: connected_agents property."""

    def test_initially_empty(self, server: OpenVIPServer) -> None:
        assert server.connected_agents == []

    def test_reflects_connected_agents(self, server: OpenVIPServer) -> None:
        with server._agent_queues_lock:
            server._agent_queues["alice"] = asyncio.Queue()
            server._agent_queues["bob"] = asyncio.Queue()
        assert sorted(server.connected_agents) == ["alice", "bob"]

# =============================================================================
# Server Lifecycle
# =============================================================================

@pytest.mark.slow
@pytest.mark.internal
class TestServerLifecycle:
    """Internal: HTTP server start/stop."""

    def test_start_stop(self, server: OpenVIPServer) -> None:
        server.start()
        assert server._running is True
        server.stop()
        assert server._running is False

    def test_double_start_is_idempotent(self, server: OpenVIPServer) -> None:
        server.start()
        try:
            t = server._thread
            server.start()
            assert server._thread is t
        finally:
            server.stop()

    def test_stop_without_start_is_safe(self, server: OpenVIPServer) -> None:
        server.stop()  # Should not raise

# =============================================================================
# SSE Status Stream
# =============================================================================

@pytest.mark.slow
@pytest.mark.internal
class TestSSEStatusStream:
    """Internal: GET /status/stream SSE behavior.

    SSE streaming requires a live HTTP server — sse-starlette's async
    generators don't work with TestClient's synchronous in-memory
    transport.

    Protocol requirements:
    - GET /status/stream returns 200 with text/event-stream
    - Sends current Status immediately on connect
    - Pushes Status on every state/agent/mode change
    - Keepalive comments every 30s if no events
    """

    def test_status_stream_documented(self) -> None:
        """SSE /status/stream protocol requirements are documented.

        Actual SSE streaming tests require a live server.
        Requirements from OpenVIP spec:
        1. Returns 200 with Content-Type: text/event-stream
        2. Sends current Status immediately on connect
        3. Each event payload is a Status object (same as GET /status)
        4. Keepalive comments (: keepalive) every 30s
        5. Events fire on state, connected_agents, or mode changes
        6. Continuously changing fields (uptime) do NOT trigger events
        """
        pass  # Protocol documentation test
