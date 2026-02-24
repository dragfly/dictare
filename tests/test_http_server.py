"""Tests for OpenVIP HTTP server (FastAPI endpoints)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dictare.core.http_server import OpenVIPServer


class MockEngine:
    """Mock engine for HTTP server tests."""

    RESERVED_AGENT_IDS = {"__keyboard__", "__tts__"}
    TTS_AGENT_ID = "__tts__"

    def __init__(self) -> None:
        self._registered_agents: list = []
        self._unregistered_agents: list[str] = []
        self._tts_calls: list[dict] = []
        self._protocol_calls: list[dict] = []

    def register_agent(self, agent) -> bool:
        self._registered_agents.append(agent)
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        self._unregistered_agents.append(agent_id)
        return True

    def get_status(self) -> dict:
        return {
            "protocol_version": "1.0",
            "state": "idle",
            "connected_agents": [],
            "uptime_seconds": 0,
            "platform": {
                "name": "Dictare",
                "version": "test",
                "state": "idle",
                "uptime_seconds": 0,
            },
        }

    def handle_speech(self, body: dict) -> dict:
        self._tts_calls.append(body)
        return {"status": "ok", "duration_ms": 100}

    def handle_protocol_command(self, body: dict) -> dict:
        self._protocol_calls.append(body)
        cmd = body.get("command", "")
        if cmd == "ping":
            return {"status": "ok", "pong": True}
        return {"status": "ok"}


class MockController:
    """Mock controller for HTTP server tests."""

    def __init__(self) -> None:
        self._app_calls: list[dict] = []

    def _handle_app_command(self, body: dict) -> dict:
        self._app_calls.append(body)
        return {"status": "ok"}


@pytest.fixture
def engine() -> MockEngine:
    return MockEngine()


@pytest.fixture
def controller() -> MockController:
    return MockController()


@pytest.fixture
def server(engine: MockEngine, controller: MockController) -> OpenVIPServer:
    return OpenVIPServer(engine, controller, host="127.0.0.1", port=0)


@pytest.fixture
def client(server: OpenVIPServer) -> TestClient:
    return TestClient(server._app)


class TestStatusEndpoint:
    """Test GET /status endpoint."""

    def test_status_returns_engine_status(self, client: TestClient) -> None:
        """GET /status returns OpenVIP spec fields at top level."""
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["protocol_version"] == "1.0"
        assert data["state"] == "idle"
        assert data["connected_agents"] == []
        assert data["uptime_seconds"] == 0
        assert "platform" in data

    def test_status_returns_json(self, client: TestClient) -> None:
        """GET /status returns valid JSON."""
        response = client.get("/status")
        assert response.headers["content-type"] == "application/json"


class TestControlEndpoint:
    """Test POST /control endpoint."""

    def test_ping_command(self, client: TestClient, engine: MockEngine) -> None:
        """POST /control with ping returns pong."""
        response = client.post("/control", json={"command": "ping"})
        assert response.status_code == 200
        assert response.json()["pong"] is True
        assert len(engine._protocol_calls) == 1

    def test_stt_start_command(self, client: TestClient, engine: MockEngine) -> None:
        """POST /control with stt.start routes to engine."""
        response = client.post("/control", json={"command": "stt.start"})
        assert response.status_code == 200
        assert engine._protocol_calls[0]["command"] == "stt.start"

    def test_protocol_command_routed_to_engine(
        self, client: TestClient, engine: MockEngine, controller: MockController
    ) -> None:
        """Protocol commands go to engine.handle_protocol_command, not controller."""
        client.post("/control", json={"command": "stt.toggle"})
        assert len(engine._protocol_calls) == 1
        assert len(controller._app_calls) == 0

    def test_app_command_routed_to_controller(
        self, client: TestClient, engine: MockEngine, controller: MockController
    ) -> None:
        """App commands go to controller._handle_app_command, not engine."""
        client.post("/control", json={"command": "output.set_mode:agents"})
        assert len(controller._app_calls) == 1
        assert len(engine._protocol_calls) == 0

    def test_unknown_command_without_controller(self, engine: MockEngine) -> None:
        """Unknown command without controller returns error."""
        server = OpenVIPServer(engine, None, host="127.0.0.1", port=0)
        client = TestClient(server._app)
        response = client.post("/control", json={"command": "foo.bar"})
        assert response.json()["status"] == "error"

    def test_control_error_returns_500(
        self, client: TestClient, engine: MockEngine
    ) -> None:
        """POST /control returns 500 on engine error."""
        engine.handle_protocol_command = MagicMock(
            side_effect=RuntimeError("boom")
        )
        response = client.post("/control", json={"command": "stt.start"})
        assert response.status_code == 500


class TestSpeechEndpoint:
    """Test POST /speech endpoint."""

    def test_tts_request(self, client: TestClient, engine: MockEngine) -> None:
        """POST /speech calls engine TTS handler."""
        body = {"openvip": "1.0", "type": "speech", "text": "Hello world"}
        response = client.post("/speech", json=body)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["duration_ms"] == 100
        assert len(engine._tts_calls) == 1
        assert engine._tts_calls[0]["text"] == "Hello world"

    def test_tts_error_returns_500(
        self, client: TestClient, engine: MockEngine
    ) -> None:
        """POST /speech returns 500 on engine error."""
        engine.handle_speech = MagicMock(side_effect=RuntimeError("TTS failed"))
        response = client.post("/speech", json={"text": "test"})
        assert response.status_code == 500


class TestPostAgentMessage:
    """Test POST /agents/{agent_id}/messages endpoint."""

    def test_post_to_unconnected_agent_returns_404(self, client: TestClient) -> None:
        """POST to non-existent agent returns 404."""
        response = client.post(
            "/agents/ghost/messages",
            json={"type": "message", "text": "hello"},
        )
        assert response.status_code == 404
        assert "not connected" in response.json()["detail"]

    def test_post_to_connected_agent(
        self, server: OpenVIPServer, client: TestClient
    ) -> None:
        """POST to connected agent queues message."""
        import asyncio

        # Manually create a queue to simulate connected agent
        queue: asyncio.Queue = asyncio.Queue()
        with server._agent_queues_lock:
            server._agent_queues["test-agent"] = queue

        response = client.post(
            "/agents/test-agent/messages",
            json={"type": "message", "text": "hello"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # Message should be in queue
        assert not queue.empty()
        msg = queue.get_nowait()
        assert msg["text"] == "hello"


class TestPutMessage:
    """Test OpenVIPServer.put_message() method."""

    def test_put_message_no_agent(self, server: OpenVIPServer) -> None:
        """put_message returns False for non-existent agent."""
        result = server.put_message("ghost", {"text": "hello"})
        assert result is False

    def test_put_message_no_loop(self, server: OpenVIPServer) -> None:
        """put_message returns False when event loop not running."""
        import asyncio

        queue: asyncio.Queue = asyncio.Queue()
        with server._agent_queues_lock:
            server._agent_queues["test"] = queue

        # No event loop running
        result = server.put_message("test", {"text": "hello"})
        assert result is False


class TestConnectedAgents:
    """Test connected_agents property."""

    def test_initially_empty(self, server: OpenVIPServer) -> None:
        """No connected agents initially."""
        assert server.connected_agents == []

    def test_agents_in_list(self, server: OpenVIPServer) -> None:
        """Connected agents appear in list."""
        import asyncio

        with server._agent_queues_lock:
            server._agent_queues["alice"] = asyncio.Queue()
            server._agent_queues["bob"] = asyncio.Queue()

        agents = server.connected_agents
        assert sorted(agents) == ["alice", "bob"]


@pytest.mark.slow
class TestServerLifecycle:
    """Test server start/stop."""

    def test_start_sets_running(self, server: OpenVIPServer) -> None:
        """start() sets _running flag."""
        server.start()
        try:
            assert server._running is True
            assert server._thread is not None
        finally:
            server.stop()

    def test_stop_clears_running(self, server: OpenVIPServer) -> None:
        """stop() clears _running flag."""
        server.start()
        server.stop()
        assert server._running is False
        assert server._thread is None

    def test_double_start_noop(self, server: OpenVIPServer) -> None:
        """Starting twice is a no-op."""
        server.start()
        try:
            thread1 = server._thread
            server.start()  # Should be no-op
            assert server._thread is thread1
        finally:
            server.stop()

    def test_stop_without_start(self, server: OpenVIPServer) -> None:
        """Stopping without starting is safe."""
        server.stop()  # Should not raise

    def test_wait_started_returns_false_on_start_error(self, server: OpenVIPServer) -> None:
        """wait_started() returns False when _start_error is set."""
        server._start_error = OSError("port in use")
        server._started.set()
        assert server.wait_started(timeout=1.0) is False

    def test_wait_started_returns_true_when_no_error(self, server: OpenVIPServer) -> None:
        """wait_started() returns True when no error was recorded."""
        server._start_error = None
        server._started.set()
        assert server.wait_started(timeout=1.0) is True

    def test_wait_started_returns_false_on_timeout(self, server: OpenVIPServer) -> None:
        """wait_started() returns False when event never fires within timeout."""
        # _started is not set — simulates server that never started
        result = server.wait_started(timeout=0.01)
        assert result is False
