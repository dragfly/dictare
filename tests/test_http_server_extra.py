"""Extra tests for OpenVIP HTTP server — endpoints with low coverage."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dictare.core.http_server import OpenVIPServer

# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

class MockEngine:
    """Mock engine for HTTP server tests."""

    RESERVED_AGENT_IDS = {"__keyboard__", "__tts__"}
    TTS_AGENT_ID = "__tts__"

    def __init__(self) -> None:
        self._registered_agents: list = []
        self._unregistered_agents: list[str] = []
        self._tts_calls: list[dict] = []
        self._protocol_calls: list[dict] = []
        self.config = MagicMock()
        self.config.tts.engine = "espeak"

    def register_agent(self, agent) -> bool:
        self._registered_agents.append(agent)
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        self._unregistered_agents.append(agent_id)
        return True

    def get_status(self) -> dict:
        return {
            "protocol_version": "1.0",
            "state": "off",
            "connected_agents": [],
            "uptime_seconds": 0,
            "platform": {
                "name": "Dictare",
                "version": "test",
                "state": "off",
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

    def stop_speaking(self) -> bool:
        return True

    def set_agent_focus(self, agent_id: str, focused: bool) -> None:
        pass

    def list_voices(self) -> list[str]:
        return ["alice", "bob"]

    def complete_tts(self, message_id: str, *, ok: bool, duration_ms: int = 0) -> None:
        pass


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


@pytest.fixture
def auth_server(engine: MockEngine, controller: MockController) -> OpenVIPServer:
    """Server with auth tokens configured."""
    return OpenVIPServer(
        engine, controller, host="127.0.0.1", port=0,
        auth_tokens={"register_tts": "secret-token"},
    )


@pytest.fixture
def auth_client(auth_server: OpenVIPServer) -> TestClient:
    return TestClient(auth_server._app)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Test GET /health endpoint."""

    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Speech stop endpoint
# ---------------------------------------------------------------------------

class TestSpeechStopEndpoint:
    """Test POST /openvip/speech/stop endpoint."""

    def test_speech_stop_returns_ok(self, client: TestClient) -> None:
        response = client.post("/openvip/speech/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["stopped"] is True


# ---------------------------------------------------------------------------
# Agent focus endpoint
# ---------------------------------------------------------------------------

class TestAgentFocusEndpoint:
    """Test POST /api/agents/{agent_id}/focus endpoint."""

    def test_set_focus_true(self, client: TestClient, engine: MockEngine) -> None:
        engine.set_agent_focus = MagicMock()
        response = client.post(
            "/api/agents/claude/focus",
            json={"focused": True},
        )
        assert response.status_code == 200
        engine.set_agent_focus.assert_called_once_with("claude", True)

    def test_set_focus_false(self, client: TestClient, engine: MockEngine) -> None:
        engine.set_agent_focus = MagicMock()
        response = client.post(
            "/api/agents/claude/focus",
            json={"focused": False},
        )
        assert response.status_code == 200
        engine.set_agent_focus.assert_called_once_with("claude", False)

    def test_invalid_focused_type(self, client: TestClient) -> None:
        response = client.post(
            "/api/agents/claude/focus",
            json={"focused": "yes"},
        )
        assert response.status_code == 400

    def test_missing_focused(self, client: TestClient) -> None:
        response = client.post(
            "/api/agents/claude/focus",
            json={},
        )
        assert response.status_code == 400

    def test_invalid_json_body(self, client: TestClient) -> None:
        response = client.post(
            "/api/agents/claude/focus",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Speech voices endpoint
# ---------------------------------------------------------------------------

class TestSpeechVoicesEndpoint:
    """Test GET /api/speech/voices endpoint."""

    def test_list_voices(self, client: TestClient) -> None:
        response = client.get("/api/speech/voices")
        assert response.status_code == 200
        data = response.json()
        assert data["engine"] == "espeak"
        assert data["voices"] == ["alice", "bob"]


# ---------------------------------------------------------------------------
# TTS complete (internal) endpoint
# ---------------------------------------------------------------------------

class TestTTSCompleteEndpoint:
    """Test POST /internal/tts/complete endpoint."""

    def test_without_auth_returns_403(self, auth_client: TestClient) -> None:
        response = auth_client.post(
            "/internal/tts/complete",
            json={"message_id": "abc", "ok": True, "duration_ms": 100},
        )
        assert response.status_code == 403

    def test_with_valid_auth(
        self, auth_client: TestClient, auth_server: OpenVIPServer
    ) -> None:
        response = auth_client.post(
            "/internal/tts/complete",
            json={"message_id": "abc", "ok": True, "duration_ms": 100},
            headers={"Authorization": "Bearer secret-token"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Reserved agent ID protection
# ---------------------------------------------------------------------------

class TestReservedAgentProtection:
    """Test that reserved agent IDs are rejected without auth."""

    def test_reserved_id_rejected_without_auth(self, auth_client: TestClient) -> None:
        """GET SSE for __tts__ without auth returns 403."""
        response = auth_client.get("/openvip/agents/__tts__/messages")
        assert response.status_code == 403

    def test_reserved_id_keyboard_rejected(self, auth_client: TestClient) -> None:
        """GET SSE for __keyboard__ without auth returns 403."""
        response = auth_client.get("/openvip/agents/__keyboard__/messages")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Duplicate agent connection
# ---------------------------------------------------------------------------

class TestDuplicateAgentConnection:
    """Test that duplicate agent connections are rejected."""

    def test_duplicate_agent_returns_409(self, server: OpenVIPServer) -> None:
        """Connecting the same agent twice returns 409."""
        # Manually register an agent queue
        with server._agent_queues_lock:
            server._agent_queues["taken"] = asyncio.Queue()

        client = TestClient(server._app)
        response = client.get("/openvip/agents/taken/messages")
        assert response.status_code == 409
        assert "already connected" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Speech endpoint — validation and edge cases
# ---------------------------------------------------------------------------

class TestSpeechEndpointExtended:
    """Test POST /openvip/speech validation."""

    def test_invalid_json_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/openvip/speech",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400

    def test_speech_engine_mismatch_returns_409(
        self, client: TestClient, engine: MockEngine
    ) -> None:
        """Speech with mismatched engine returns 409."""
        engine.handle_speech = MagicMock(
            side_effect=ValueError("wrong engine")
        )
        body = {
            "openvip": "1.0", "type": "speech",
            "id": "660e8400-e29b-41d4-a716-446655440001",
            "timestamp": "2026-02-06T10:30:05Z",
            "text": "Hello",
        }
        response = client.post("/openvip/speech", json=body)
        assert response.status_code == 409

    def test_speech_error_status_returns_400(
        self, client: TestClient, engine: MockEngine
    ) -> None:
        """Speech returning error status returns 400."""
        engine.handle_speech = MagicMock(
            return_value={"status": "error", "error": "No text provided"}
        )
        body = {
            "openvip": "1.0", "type": "speech",
            "id": "660e8400-e29b-41d4-a716-446655440001",
            "timestamp": "2026-02-06T10:30:05Z",
            "text": "",
        }
        response = client.post("/openvip/speech", json=body)
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Post agent message — validation
# ---------------------------------------------------------------------------

class TestPostAgentMessageValidation:
    """Test POST /openvip/agents/{agent_id}/messages validation."""

    def test_invalid_json_returns_400(self, server: OpenVIPServer) -> None:
        """Invalid JSON body returns 400."""
        with server._agent_queues_lock:
            server._agent_queues["test"] = asyncio.Queue()

        client = TestClient(server._app)
        response = client.post(
            "/openvip/agents/test/messages",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400
        assert "INVALID_FORMAT" in response.json().get("code", "")

    def test_invalid_openvip_message_returns_400(self, server: OpenVIPServer) -> None:
        """Message that fails OpenVIP validation returns 400."""
        with server._agent_queues_lock:
            server._agent_queues["test"] = asyncio.Queue()

        client = TestClient(server._app)
        # Missing required fields (openvip, type, id, timestamp)
        response = client.post(
            "/openvip/agents/test/messages",
            json={"foo": "bar"},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# OpenVIP spec endpoint
# ---------------------------------------------------------------------------

class TestOpenVIPSpecEndpoint:
    """Test GET /openvip/openapi.json endpoint."""

    def test_spec_returns_json(self, client: TestClient) -> None:
        response = client.get("/openvip/openapi.json")
        # May be 200 or 404 depending on whether spec file exists
        assert response.status_code in (200, 404)

    def test_spec_missing_returns_404(self, client: TestClient) -> None:
        """When spec file doesn't exist, returns 404."""
        with patch("pathlib.Path.exists", return_value=False):
            response = client.get("/openvip/openapi.json")
            assert response.status_code == 404


# ---------------------------------------------------------------------------
# Control endpoint — extended
# ---------------------------------------------------------------------------

class TestControlEndpointExtended:
    """Test POST /openvip/control — additional commands."""

    def test_engine_shutdown_routes_to_engine(
        self, client: TestClient, engine: MockEngine
    ) -> None:
        response = client.post(
            "/openvip/control", json={"command": "engine.shutdown"}
        )
        assert response.status_code == 200
        assert engine._protocol_calls[0]["command"] == "engine.shutdown"

    def test_engine_restart_routes_to_engine(
        self, client: TestClient, engine: MockEngine
    ) -> None:
        response = client.post(
            "/openvip/control", json={"command": "engine.restart"}
        )
        assert response.status_code == 200
        assert engine._protocol_calls[0]["command"] == "engine.restart"

    def test_hotkey_capture_routes_to_engine(
        self, client: TestClient, engine: MockEngine
    ) -> None:
        response = client.post(
            "/openvip/control", json={"command": "hotkey.capture"}
        )
        assert response.status_code == 200
        assert engine._protocol_calls[0]["command"] == "hotkey.capture"

    def test_app_command_set_mode(
        self, client: TestClient, controller: MockController
    ) -> None:
        response = client.post(
            "/openvip/control", json={"command": "output.set_mode:keyboard"}
        )
        assert response.status_code == 200
        assert controller._app_calls[0]["command"] == "output.set_mode:keyboard"


# ---------------------------------------------------------------------------
# put_message edge cases
# ---------------------------------------------------------------------------

class TestPutMessageEdgeCases:
    """Additional tests for OpenVIPServer.put_message()."""

    def test_put_message_to_existing_agent_with_loop(self, server: OpenVIPServer) -> None:
        """put_message succeeds when event loop is running."""
        q: asyncio.Queue = asyncio.Queue()
        with server._agent_queues_lock:
            server._agent_queues["test"] = q

        loop = asyncio.new_event_loop()
        server._loop = loop

        import threading

        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        try:
            result = server.put_message("test", {"text": "hello"})
            assert result is True
        finally:
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=2)
            loop.close()


# ---------------------------------------------------------------------------
# notify_status_change
# ---------------------------------------------------------------------------

class TestNotifyStatusChange:
    """Test notify_status_change method."""

    def test_notify_pushes_to_queues(self, server: OpenVIPServer) -> None:
        """notify_status_change pushes status to all subscribed queues."""
        q: asyncio.Queue = asyncio.Queue()
        with server._status_queues_lock:
            server._status_queues.append(q)

        loop = asyncio.new_event_loop()
        server._loop = loop

        import threading

        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        try:
            server.notify_status_change()
            # Give time for the coroutine to execute
            import time
            deadline = time.monotonic() + 2
            while q.empty() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert not q.empty()
        finally:
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=2)
            loop.close()


# ---------------------------------------------------------------------------
# has_permission
# ---------------------------------------------------------------------------

class TestHasPermission:
    """Test _has_permission method."""

    def test_no_token_configured(self, server: OpenVIPServer) -> None:
        """Returns False if no token for the permission."""
        req = MagicMock()
        req.headers = {"authorization": "Bearer something"}
        assert server._has_permission(req, "nonexistent") is False

    def test_correct_bearer_token(self, auth_server: OpenVIPServer) -> None:
        req = MagicMock()
        req.headers = {"authorization": "Bearer secret-token"}
        assert auth_server._has_permission(req, "register_tts") is True

    def test_wrong_bearer_token(self, auth_server: OpenVIPServer) -> None:
        req = MagicMock()
        req.headers = {"authorization": "Bearer wrong-token"}
        assert auth_server._has_permission(req, "register_tts") is False

    def test_missing_auth_header(self, auth_server: OpenVIPServer) -> None:
        req = MagicMock()
        req.headers = {}
        assert auth_server._has_permission(req, "register_tts") is False


# ---------------------------------------------------------------------------
# is_tts_connected / wait_tts_connected
# ---------------------------------------------------------------------------

class TestTTSConnectedEvents:
    """Test TTS connection tracking."""

    def test_initially_not_connected(self, server: OpenVIPServer) -> None:
        assert server.is_tts_connected() is False

    def test_set_then_check(self, server: OpenVIPServer) -> None:
        server._tts_connected_event.set()
        assert server.is_tts_connected() is True

    def test_wait_returns_false_on_timeout(self, server: OpenVIPServer) -> None:
        assert server.wait_tts_connected(timeout=0.01) is False

    def test_wait_returns_true_when_set(self, server: OpenVIPServer) -> None:
        server._tts_connected_event.set()
        assert server.wait_tts_connected(timeout=0.01) is True


# ---------------------------------------------------------------------------
# System info endpoint
# ---------------------------------------------------------------------------

class TestSystemInfoEndpoint:
    """Test GET /api/system endpoint."""

    def test_returns_platform(self, client: TestClient) -> None:
        response = client.get("/api/system")
        assert response.status_code == 200
        assert "platform" in response.json()
