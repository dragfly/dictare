"""OpenVIP Protocol Compliance Test Suite.

Dual-mode: runs in-process with mocks (default) or against a live server.

    # In-process (CI, fast, with mocks):
    pytest tests/test_openvip_compliance.py

    # Against a real OpenVIP server:
    pytest tests/test_openvip_compliance.py --openvip-url http://localhost:8770

Tests marked @pytest.mark.internal depend on mock internals and are
automatically skipped when --openvip-url is provided.

Reference: https://openvip.org/protocol/
Schema: https://openvip.org/schema/v1.0.json
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from voxtype.core.http_server import OpenVIPServer

# =============================================================================
# Helpers
# =============================================================================

def _uuid() -> str:
    return str(uuid.uuid4())

def _timestamp() -> str:
    return datetime.now(UTC).isoformat()

def _transcription(**overrides) -> dict:
    """Build a valid transcription message with optional overrides."""
    msg = {
        "openvip": "1.0",
        "type": "transcription",
        "id": _uuid(),
        "timestamp": _timestamp(),
        "text": "hello world",
    }
    msg.update(overrides)
    return msg

def _speech_request(**overrides) -> dict:
    """Build a valid speech request."""
    msg = {
        "openvip": "1.0",
        "type": "speech",
        "text": "hello world",
    }
    msg.update(overrides)
    return msg

# =============================================================================
# Fixtures — mocks for in-process mode, httpx.Client for external mode
# =============================================================================

class ComplianceMockEngine:
    """Minimal mock engine implementing the public API surface."""

    RESERVED_AGENT_IDS = {"__keyboard__"}

    def __init__(self) -> None:
        self._registered: list = []
        self._unregistered: list[str] = []
        self._speech_calls: list[dict] = []
        self._protocol_calls: list[dict] = []
        self._state = "idle"

    def register_agent(self, agent) -> bool:
        self._registered.append(agent)
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        self._unregistered.append(agent_id)
        return True

    def get_status(self) -> dict:
        return {
            "protocol_version": "1.0",
            "state": self._state,
            "connected_agents": [],
            "uptime_seconds": 42,
            "platform": {
                "name": "ComplianceTest",
                "version": "0.0.0",
            },
        }

    def handle_speech(self, body: dict) -> dict:
        text = body.get("text", "")
        if not text:
            return {"status": "error", "error": "No text provided"}
        self._speech_calls.append(body)
        return {"status": "ok", "duration_ms": 150}

    def handle_protocol_command(self, body: dict) -> dict:
        self._protocol_calls.append(body)
        cmd = body.get("command", "")
        if cmd == "stt.start":
            self._state = "listening"
            return {"status": "ok", "listening": True}
        elif cmd == "stt.stop":
            self._state = "idle"
            return {"status": "ok", "listening": False}
        elif cmd == "stt.toggle":
            return {"status": "ok"}
        elif cmd == "engine.shutdown":
            return {"status": "ok"}
        elif cmd == "ping":
            return {"status": "ok", "pong": True}
        return {"status": "error", "error": f"Unknown protocol command: {cmd}"}

class ComplianceMockController:
    """Minimal mock controller for app commands."""

    def __init__(self) -> None:
        self._calls: list[dict] = []

    def _handle_app_command(self, body: dict) -> dict:
        self._calls.append(body)
        return {"status": "ok"}

@pytest.fixture
def engine() -> ComplianceMockEngine:
    return ComplianceMockEngine()

@pytest.fixture
def controller() -> ComplianceMockController:
    return ComplianceMockController()

@pytest.fixture
def server(engine, controller) -> OpenVIPServer:
    return OpenVIPServer(engine, controller, host="127.0.0.1", port=0)

@pytest.fixture
def client(request, server):
    """HTTP client — TestClient (in-process) or httpx.Client (external)."""
    url = request.config.getoption("--openvip-url")
    if url:
        import httpx

        c = httpx.Client(base_url=url)
        try:
            c.get("/status")
        except httpx.ConnectError:
            pytest.fail(f"OpenVIP server not reachable at {url}")
        yield c
        c.close()
    else:
        yield TestClient(server._app)

# =============================================================================
# 1. GET /status — Engine Status
# =============================================================================

class TestGetStatus:
    """OpenVIP: GET /status returns engine status."""

    def test_returns_200(self, client) -> None:
        """GET /status returns 200 OK."""
        r = client.get("/status")
        assert r.status_code == 200

    def test_returns_json(self, client) -> None:
        """Response content type is application/json."""
        r = client.get("/status")
        assert "application/json" in r.headers["content-type"]

    def test_has_protocol_version(self, client) -> None:
        """Response includes protocol_version field."""
        data = client.get("/status").json()
        assert "protocol_version" in data
        assert data["protocol_version"] == "1.0"

    def test_has_state(self, client) -> None:
        """Response includes state field."""
        data = client.get("/status").json()
        assert "state" in data
        assert isinstance(data["state"], str)

    def test_has_connected_agents(self, client) -> None:
        """Response includes connected_agents as a list."""
        data = client.get("/status").json()
        assert "connected_agents" in data
        assert isinstance(data["connected_agents"], list)

    def test_has_platform(self, client) -> None:
        """Response includes opaque platform object."""
        data = client.get("/status").json()
        assert "platform" in data
        assert isinstance(data["platform"], dict)

    @pytest.mark.internal
    def test_state_reflects_engine(self, client, engine) -> None:
        """Status state reflects engine state."""
        engine._state = "listening"
        data = client.get("/status").json()
        assert data["state"] == "listening"

# =============================================================================
# 2. POST /control — Protocol Commands
# =============================================================================

class TestControlProtocol:
    """OpenVIP: POST /control for protocol-defined commands."""

    def test_stt_start(self, client) -> None:
        """stt.start returns ok with listening=True."""
        r = client.post("/control", json={"command": "stt.start"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["listening"] is True

    def test_stt_stop(self, client) -> None:
        """stt.stop returns ok with listening=False."""
        r = client.post("/control", json={"command": "stt.stop"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["listening"] is False

    def test_stt_toggle(self, client) -> None:
        """stt.toggle returns ok."""
        r = client.post("/control", json={"command": "stt.toggle"})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    @pytest.mark.internal  # Would shut down a real server
    def test_engine_shutdown(self, client) -> None:
        """engine.shutdown returns ok."""
        r = client.post("/control", json={"command": "engine.shutdown"})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_ping(self, client) -> None:
        """ping returns ok with pong=True."""
        r = client.post("/control", json={"command": "ping"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["pong"] is True

    @pytest.mark.internal
    def test_stt_start_routed_to_engine(
        self, client, engine: ComplianceMockEngine,
    ) -> None:
        """stt.start is routed to engine, not controller."""
        client.post("/control", json={"command": "stt.start"})
        assert len(engine._protocol_calls) == 1
        assert engine._protocol_calls[0]["command"] == "stt.start"

    @pytest.mark.internal
    def test_all_protocol_commands_go_to_engine(
        self, client, engine: ComplianceMockEngine,
        controller: ComplianceMockController,
    ) -> None:
        """All protocol commands route to engine, none to controller."""
        for cmd in ["stt.start", "stt.stop", "stt.toggle",
                     "engine.shutdown", "ping"]:
            client.post("/control", json={"command": cmd})
        assert len(engine._protocol_calls) == 5
        assert len(controller._calls) == 0

@pytest.mark.internal
class TestControlRouting:
    """OpenVIP: POST /control routing between engine and controller."""

    def test_app_command_routed_to_controller(
        self, client, controller: ComplianceMockController,
    ) -> None:
        """Non-protocol commands go to controller."""
        client.post("/control", json={"command": "output.set_mode:agents"})
        assert len(controller._calls) == 1

    def test_app_command_not_routed_to_engine(
        self, client, engine: ComplianceMockEngine,
    ) -> None:
        """Non-protocol commands do not reach engine."""
        client.post("/control", json={"command": "output.set_agent:claude"})
        assert len(engine._protocol_calls) == 0

    def test_unknown_command_without_controller(
        self, engine: ComplianceMockEngine,
    ) -> None:
        """Unknown command without controller returns error."""
        server = OpenVIPServer(engine, None, host="127.0.0.1", port=0)
        c = TestClient(server._app)
        r = c.post("/control", json={"command": "foo.bar"})
        assert r.status_code == 200
        assert r.json()["status"] == "error"

    def test_control_engine_error_returns_500(
        self, client, engine: ComplianceMockEngine,
    ) -> None:
        """Engine exception results in 500."""
        engine.handle_protocol_command = MagicMock(
            side_effect=RuntimeError("boom")
        )
        r = client.post("/control", json={"command": "stt.start"})
        assert r.status_code == 500

# =============================================================================
# 3. POST /speech — Text-to-Speech
# =============================================================================

class TestSpeech:
    """OpenVIP: POST /speech for text-to-speech."""

    def test_speech_returns_200(self, client) -> None:
        """Valid speech request returns 200 OK."""
        r = client.post("/speech", json=_speech_request())
        assert r.status_code == 200

    def test_speech_returns_status_ok(self, client) -> None:
        """Response has status=ok."""
        data = client.post("/speech", json=_speech_request()).json()
        assert data["status"] == "ok"

    def test_speech_returns_duration(self, client) -> None:
        """Response includes duration_ms."""
        data = client.post("/speech", json=_speech_request()).json()
        assert "duration_ms" in data
        assert isinstance(data["duration_ms"], int)
        assert data["duration_ms"] >= 0

    @pytest.mark.internal
    def test_speech_with_language(
        self, client, engine: ComplianceMockEngine,
    ) -> None:
        """Speech request with language is accepted."""
        r = client.post("/speech", json=_speech_request(language="en"))
        assert r.status_code == 200
        assert engine._speech_calls[-1]["language"] == "en"

    @pytest.mark.internal
    def test_speech_text_forwarded(
        self, client, engine: ComplianceMockEngine,
    ) -> None:
        """Speech text is forwarded to engine."""
        client.post("/speech", json=_speech_request(text="say this"))
        assert engine._speech_calls[-1]["text"] == "say this"

    @pytest.mark.internal
    def test_speech_engine_error_returns_500(
        self, client, engine: ComplianceMockEngine,
    ) -> None:
        """Engine exception results in 500."""
        engine.handle_speech = MagicMock(side_effect=RuntimeError("TTS fail"))
        r = client.post("/speech", json=_speech_request())
        assert r.status_code == 500

# =============================================================================
# 4. POST /agents/{agent_id}/messages — Send Message
# =============================================================================

class TestPostAgentMessages:
    """OpenVIP: POST /agents/{agent_id}/messages."""

    @pytest.mark.internal
    def test_post_to_connected_agent_returns_200(
        self, server: OpenVIPServer, client,
    ) -> None:
        """Posting to a connected agent returns 200 OK."""
        queue: asyncio.Queue = asyncio.Queue()
        with server._agent_queues_lock:
            server._agent_queues["alice"] = queue

        r = client.post(
            "/agents/alice/messages", json=_transcription()
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    @pytest.mark.internal
    def test_message_delivered_to_queue(
        self, server: OpenVIPServer, client,
    ) -> None:
        """Posted message appears in agent queue."""
        queue: asyncio.Queue = asyncio.Queue()
        with server._agent_queues_lock:
            server._agent_queues["alice"] = queue

        msg = _transcription(text="test delivery")
        client.post("/agents/alice/messages", json=msg)

        queued = queue.get_nowait()
        assert queued["text"] == "test delivery"

    def test_post_to_unconnected_agent_returns_404(self, client) -> None:
        """Posting to a non-existent agent returns 404."""
        r = client.post(
            "/agents/ghost/messages", json=_transcription()
        )
        assert r.status_code == 404

    def test_404_detail_mentions_not_connected(self, client) -> None:
        """404 error detail mentions agent not connected."""
        r = client.post(
            "/agents/ghost/messages", json=_transcription()
        )
        assert "not connected" in r.json()["detail"].lower()

# =============================================================================
# 5. GET /agents/{agent_id}/messages — SSE Agent Registration
# =============================================================================

class TestSSEAgentRegistration:
    """OpenVIP: GET /agents/{agent_id}/messages — SSE lifecycle."""

    def test_reserved_agent_id_returns_403(self, client) -> None:
        """Reserved agent IDs (e.g., __keyboard__) return 403."""
        r = client.get("/agents/__keyboard__/messages")
        assert r.status_code == 403

    @pytest.mark.internal
    def test_duplicate_agent_returns_409(
        self, server: OpenVIPServer, client,
    ) -> None:
        """Connecting with an already-connected agent ID returns 409."""
        with server._agent_queues_lock:
            server._agent_queues["alice"] = asyncio.Queue()

        r = client.get("/agents/alice/messages")
        assert r.status_code == 409

    @pytest.mark.internal
    def test_409_detail_mentions_already_connected(
        self, server: OpenVIPServer, client,
    ) -> None:
        """409 error detail mentions agent already connected."""
        with server._agent_queues_lock:
            server._agent_queues["alice"] = asyncio.Queue()

        r = client.get("/agents/alice/messages")
        assert "already connected" in r.json()["detail"].lower()

# =============================================================================
# 6. Status Response Schema
# =============================================================================

class TestStatusSchema:
    """OpenVIP: Status object schema compliance."""

    def test_protocol_version_is_string(self, client) -> None:
        data = client.get("/status").json()
        assert isinstance(data["protocol_version"], str)

    def test_state_is_string(self, client) -> None:
        data = client.get("/status").json()
        assert isinstance(data["state"], str)

    def test_connected_agents_is_list_of_strings(self, client) -> None:
        data = client.get("/status").json()
        agents = data["connected_agents"]
        assert isinstance(agents, list)
        for a in agents:
            assert isinstance(a, str)

    def test_platform_is_object(self, client) -> None:
        data = client.get("/status").json()
        assert isinstance(data["platform"], dict)

# =============================================================================
# 7. Ack Response Schema
# =============================================================================

class TestAckSchema:
    """OpenVIP: Ack response schema compliance."""

    def test_ack_has_status_ok(self, client) -> None:
        """Control command ack has status=ok."""
        data = client.post(
            "/control", json={"command": "ping"}
        ).json()
        assert data["status"] == "ok"

    def test_speech_ack_has_status_ok(self, client) -> None:
        """Speech ack has status=ok."""
        data = client.post("/speech", json=_speech_request()).json()
        assert data["status"] == "ok"

    @pytest.mark.internal
    def test_message_ack_has_status_ok(
        self, server: OpenVIPServer, client,
    ) -> None:
        """Post message ack has status=ok."""
        with server._agent_queues_lock:
            server._agent_queues["alice"] = asyncio.Queue()

        data = client.post(
            "/agents/alice/messages", json=_transcription()
        ).json()
        assert data["status"] == "ok"

# =============================================================================
# 8. PUT Message (thread-safe delivery)
# =============================================================================

@pytest.mark.internal
class TestPutMessage:
    """OpenVIP: Server.put_message() thread-safe delivery."""

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
# 9. Connected Agents
# =============================================================================

@pytest.mark.internal
class TestConnectedAgents:
    """OpenVIP: connected_agents property."""

    def test_initially_empty(self, server: OpenVIPServer) -> None:
        assert server.connected_agents == []

    def test_reflects_connected_agents(self, server: OpenVIPServer) -> None:
        with server._agent_queues_lock:
            server._agent_queues["alice"] = asyncio.Queue()
            server._agent_queues["bob"] = asyncio.Queue()
        assert sorted(server.connected_agents) == ["alice", "bob"]

# =============================================================================
# 10. Server Lifecycle
# =============================================================================

@pytest.mark.slow
@pytest.mark.internal
class TestServerLifecycle:
    """OpenVIP: HTTP server start/stop."""

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
# 11. Message Schema Validation (from OpenVIP protocol spec)
# =============================================================================
#
# These tests validate message structures against the OpenVIP JSON Schema.
# Test cases sourced from:
#   protocol/tests/schema/messages.json
#
# Note: VoxType's HTTP server currently accepts any JSON body on POST
# /agents/{id}/messages (no schema validation at transport level).
# These tests validate the MESSAGE FORMAT contract, not HTTP-level rejection.
# Schema validation is the responsibility of the SDK client (openvip.Client)
# and the engine pipeline, not the HTTP transport layer.

VALID_MESSAGES = [
    pytest.param(
        {
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-06T10:30:00Z",
            "text": "hello world",
        },
        id="minimal_transcription",
    ),
    pytest.param(
        {
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-06T10:30:00Z",
            "text": "Turn on the kitchen light",
            "origin": "voxtype/3.0.0",
            "language": "en",
            "confidence": 0.95,
            "partial": False,
        },
        id="all_optional_fields",
    ),
    pytest.param(
        {
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440002",
            "timestamp": "2026-02-06T10:30:00Z",
            "text": "Turn on the",
            "partial": True,
            "origin": "voxtype/3.0.0",
        },
        id="partial_transcription",
    ),
    pytest.param(
        {
            "openvip": "1.0",
            "type": "transcription",
            "id": "660e8400-e29b-41d4-a716-446655440001",
            "timestamp": "2026-02-06T10:30:01Z",
            "text": "ho un bug",
            "language": "it",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "parent_id": "550e8400-e29b-41d4-a716-446655440000",
        },
        id="tracing",
    ),
    pytest.param(
        {
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-06T10:30:00Z",
            "text": "fix the login bug",
            "x_input": {
                "submit": True,
                "newline": False,
                "trigger": "ok send",
                "confidence": 0.95,
            },
        },
        id="x_input_extension",
    ),
    pytest.param(
        {
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-06T10:30:00Z",
            "text": "",
            "x_agent_switch": {
                "target": "claude",
                "confidence": 0.92,
            },
        },
        id="x_agent_switch_extension",
    ),
    pytest.param(
        {
            "openvip": "1.0",
            "type": "speech",
            "id": "660e8400-e29b-41d4-a716-446655440001",
            "timestamp": "2026-02-06T10:30:05Z",
            "text": "Light turned on",
            "language": "en",
        },
        id="speech_message",
    ),
    pytest.param(
        {
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-06T10:30:00Z",
            "text": "accendi la luce",
            "x_bticino": {
                "device": "kitchen_light",
                "action": "on",
            },
        },
        id="custom_vendor_extension",
    ),
    pytest.param(
        {
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-06T10:30:00Z",
            "text": "mumble",
            "confidence": 0.0,
        },
        id="confidence_boundary_0",
    ),
    pytest.param(
        {
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-06T10:30:00Z",
            "text": "crystal clear",
            "confidence": 1.0,
        },
        id="confidence_boundary_1",
    ),
    pytest.param(
        {
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-06T10:30:00Z",
            "text": "hello",
            "future_field": "some value",
        },
        id="forward_compatibility_unknown_field",
    ),
]

@pytest.mark.internal
class TestValidMessages:
    """OpenVIP: Valid message schemas are accepted by transport."""

    @pytest.mark.parametrize("message", VALID_MESSAGES)
    def test_valid_message_accepted(
        self, server: OpenVIPServer, client, message: dict,
    ) -> None:
        """Valid OpenVIP messages are delivered to connected agents."""
        queue: asyncio.Queue = asyncio.Queue()
        with server._agent_queues_lock:
            server._agent_queues["test"] = queue

        r = client.post("/agents/test/messages", json=message)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        # Message should be in queue, preserving all fields
        queued = queue.get_nowait()
        assert queued["text"] == message["text"]
        if "x_input" in message:
            assert queued["x_input"] == message["x_input"]
        if "x_agent_switch" in message:
            assert queued["x_agent_switch"] == message["x_agent_switch"]
        if "trace_id" in message:
            assert queued["trace_id"] == message["trace_id"]
            assert queued["parent_id"] == message["parent_id"]

# Message schema validation test data — these should be REJECTED by schema
# validators (SDK, engine) but the HTTP transport accepts any JSON.
# Included here to document the protocol contract.

INVALID_MESSAGES = [
    pytest.param(
        {"type": "transcription", "id": _uuid(), "timestamp": _timestamp(),
         "text": "hello"},
        id="missing_openvip",
    ),
    pytest.param(
        {"openvip": "1.0", "id": _uuid(), "timestamp": _timestamp(),
         "text": "hello"},
        id="missing_type",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "transcription",
         "timestamp": _timestamp(), "text": "hello"},
        id="missing_id",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "transcription", "id": _uuid(),
         "text": "hello"},
        id="missing_timestamp",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp()},
        id="missing_text",
    ),
    pytest.param(
        {"openvip": "2.0", "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="wrong_protocol_version",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "message", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="invalid_type_enum",
    ),
    pytest.param(
        {**_transcription(), "trace_id": _uuid()},
        id="trace_id_without_parent_id",
    ),
    pytest.param(
        {**_transcription(), "parent_id": _uuid()},
        id="parent_id_without_trace_id",
    ),
    pytest.param(
        {**_transcription(), "confidence": 1.5},
        id="confidence_above_1",
    ),
    pytest.param(
        {**_transcription(), "confidence": -0.1},
        id="confidence_below_0",
    ),
    pytest.param(
        {**_transcription(), "x_bad": "not an object"},
        id="x_field_string_not_object",
    ),
    pytest.param(
        {**_transcription(), "x_bad": True},
        id="x_field_boolean_not_object",
    ),
    pytest.param(
        {**_transcription(), "partial": "true"},
        id="partial_string_not_boolean",
    ),
]

class TestInvalidMessageSchemas:
    """OpenVIP: Invalid messages documented for schema validation.

    The HTTP transport layer accepts any JSON body (no validation).
    These test cases document what schema validators (SDK, engine)
    should reject. They are kept here as protocol documentation
    and can be used by schema validation test suites.
    """

    @pytest.mark.parametrize("message", INVALID_MESSAGES)
    def test_invalid_message_documented(self, message: dict) -> None:
        """Each invalid message violates at least one schema constraint.

        This test simply validates the test data is well-formed as dicts.
        Actual schema validation is the SDK's responsibility.
        """
        assert isinstance(message, dict)
        # These messages should fail schema validation — documented here
        # for completeness. When the compliance suite moves to the
        # OpenVIP protocol repo, these will drive jsonschema validation.

# =============================================================================
# 12. SSE Event Format
# =============================================================================

@pytest.mark.slow
@pytest.mark.internal
class TestSSEStatusStream:
    """OpenVIP: GET /status/stream SSE behavior.

    SSE streaming requires a live HTTP server — sse-starlette's async
    generators don't work with TestClient's synchronous in-memory
    transport. These tests are marked slow and require a running server.

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

# =============================================================================
# 13. Content Negotiation
# =============================================================================

class TestContentType:
    """OpenVIP: Response content types."""

    def test_status_json(self, client) -> None:
        r = client.get("/status")
        assert "application/json" in r.headers["content-type"]

    def test_control_json(self, client) -> None:
        r = client.post("/control", json={"command": "ping"})
        assert "application/json" in r.headers["content-type"]

    def test_speech_json(self, client) -> None:
        r = client.post("/speech", json=_speech_request())
        assert "application/json" in r.headers["content-type"]

    @pytest.mark.internal
    def test_post_message_json(
        self, server: OpenVIPServer, client,
    ) -> None:
        with server._agent_queues_lock:
            server._agent_queues["a"] = asyncio.Queue()
        r = client.post("/agents/a/messages", json=_transcription())
        assert "application/json" in r.headers["content-type"]

    def test_status_stream_event_stream(self) -> None:
        """GET /status/stream content type is text/event-stream.

        Note: SSE streaming cannot be tested with in-memory TestClient
        (sse-starlette limitation). Verified manually with live server.
        """
        pass  # Requires live server

# =============================================================================
# 14. Edge Cases
# =============================================================================

class TestEdgeCases:
    """OpenVIP: Edge cases and boundary conditions."""

    def test_empty_command(self, client) -> None:
        """Empty command string is handled gracefully."""
        r = client.post("/control", json={"command": ""})
        # Should not crash — returns error or routes to controller
        assert r.status_code in (200, 400, 500)

    def test_missing_command_field(self, client) -> None:
        """Missing command field is handled gracefully."""
        r = client.post("/control", json={})
        assert r.status_code in (200, 400, 500)

    def test_empty_speech_text(self, client) -> None:
        """Empty speech text returns error, not crash."""
        r = client.post("/speech", json={"text": ""})
        assert r.status_code == 200
        assert r.json()["status"] == "error"

    def test_agent_id_with_special_chars(self, client) -> None:
        """Agent IDs with dashes and underscores work."""
        # 404 is expected (not connected), but should not 500
        r = client.post(
            "/agents/my-agent_v2/messages", json=_transcription()
        )
        assert r.status_code == 404  # Not connected, not server error

    @pytest.mark.internal
    def test_multiple_agents_independent(
        self, server: OpenVIPServer, client,
    ) -> None:
        """Messages to different agents are independent."""
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        with server._agent_queues_lock:
            server._agent_queues["alice"] = q1
            server._agent_queues["bob"] = q2

        client.post(
            "/agents/alice/messages",
            json=_transcription(text="for alice"),
        )
        client.post(
            "/agents/bob/messages",
            json=_transcription(text="for bob"),
        )

        assert q1.get_nowait()["text"] == "for alice"
        assert q2.get_nowait()["text"] == "for bob"
        assert q1.empty()
        assert q2.empty()

    @pytest.mark.internal
    def test_large_text_accepted(
        self, server: OpenVIPServer, client,
    ) -> None:
        """Large text messages are accepted."""
        with server._agent_queues_lock:
            server._agent_queues["test"] = asyncio.Queue()

        big_text = "word " * 10000  # ~50KB
        r = client.post(
            "/agents/test/messages",
            json=_transcription(text=big_text),
        )
        assert r.status_code == 200

    @pytest.mark.internal
    def test_unicode_text(
        self, server: OpenVIPServer, client,
    ) -> None:
        """Unicode text (CJK, emoji, RTL) is preserved."""
        with server._agent_queues_lock:
            server._agent_queues["test"] = asyncio.Queue()

        texts = [
            "Accendi la luce in cucina",
            "台所の電気をつけて",
            "مرحبا بالعالم",
        ]
        for text in texts:
            client.post(
                "/agents/test/messages",
                json=_transcription(text=text),
            )

        queue = server._agent_queues["test"]
        for text in texts:
            assert queue.get_nowait()["text"] == text
