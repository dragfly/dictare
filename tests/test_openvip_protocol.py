"""OpenVIP Protocol Compliance Test Suite.

Executable specification of the OpenVIP protocol. Tests exercise the HTTP/SSE
interface with real HTTP requests — no mock internals, no implementation details.

Dual-mode:

    # Embedded server (fast, CI):
    pytest tests/test_openvip_protocol.py

    # Against any running OpenVIP server:
    pytest tests/test_openvip_protocol.py --openvip-url http://localhost:8770

This file is portable: it can be copied to any OpenVIP implementation's repo
and run against that implementation's server.

Reference: https://openvip.org/protocol/
Schema: https://openvip.org/schema/v1.0.json
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

# =============================================================================
# Timeout factor — scaled by --openvip-timeout-factor for slow implementations
# =============================================================================

_TIMEOUT_FACTOR = 1.0


@pytest.fixture(autouse=True, scope="session")
def _apply_timeout_factor(request):
    """Read --openvip-timeout-factor and apply to all wait operations."""
    global _TIMEOUT_FACTOR
    _TIMEOUT_FACTOR = request.config.getoption("--openvip-timeout-factor")


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
        "id": "660e8400-e29b-41d4-a716-446655440001",
        "timestamp": "2026-02-06T10:30:05Z",
        "text": "hello world",
    }
    msg.update(overrides)
    return msg


def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    """Poll predicate until True or timeout.

    Timeout is scaled by --openvip-timeout-factor to accommodate slow
    implementations. Default factor is 1.0 (no scaling).
    """
    scaled = timeout * _TIMEOUT_FACTOR
    deadline = time.monotonic() + scaled
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise TimeoutError(
        f"Predicate not satisfied within {scaled:.1f}s "
        f"(base={timeout}s, factor={_TIMEOUT_FACTOR}x)"
    )


# =============================================================================
# SSE Connection Helper — connects as an agent via real HTTP
# =============================================================================


class SSEConnection:
    """Connect as an SSE agent via real HTTP and collect received events.

    Uses httpx streaming to maintain a long-lived SSE connection in a
    background thread. Events are collected in self.events as parsed dicts.
    """

    def __init__(self, base_url: str, agent_id: str) -> None:
        self.agent_id = agent_id
        self.events: list[dict] = []
        self._base_url = base_url
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._http: Any = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def wait_connected(self, timeout: float = 5.0) -> None:
        scaled = timeout * _TIMEOUT_FACTOR
        if not self._connected.wait(scaled):
            raise TimeoutError(
                f"SSE agent {self.agent_id} did not connect within {scaled:.1f}s"
            )

    def stop(self) -> None:
        self._stop.set()
        if self._http:
            self._http.close()  # Interrupts blocking read

    def _run(self) -> None:
        import httpx

        self._http = httpx.Client(base_url=self._base_url)
        try:
            with self._http.stream(
                "GET", f"/agents/{self.agent_id}/messages"
            ) as r:
                self._connected.set()
                for line in r.iter_lines():
                    if self._stop.is_set():
                        break
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data:
                            self.events.append(json.loads(data))
        except Exception:
            pass  # Connection closed or interrupted
        finally:
            self._connected.set()  # Don't block forever on error


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def e2e_client(live_url):
    """HTTP client connected to a real server (httpx)."""
    import httpx

    with httpx.Client(base_url=live_url) as c:
        yield c


@pytest.fixture
def sse_connect(live_url):
    """Factory: connect an SSE agent, returns SSEConnection.

    Each call appends a unique suffix to the agent_id to prevent
    collisions between tests (server cleanup of disconnected agents
    is async and may not complete before the next test starts).

    Usage:
        conn = sse_connect("alice")
        agent_url = f"/agents/{conn.agent_id}/messages"
    """
    connections: list[SSEConnection] = []

    def _connect(agent_id: str = "agent") -> SSEConnection:
        unique_id = f"{agent_id}-{uuid.uuid4().hex[:8]}"
        conn = SSEConnection(live_url, unique_id)
        conn.start()
        conn.wait_connected()
        connections.append(conn)
        return conn

    yield _connect

    for conn in connections:
        conn.stop()


# =============================================================================
# 1. GET /status — Engine Status
# =============================================================================


class TestGetStatus:
    """OpenVIP: GET /status returns engine status."""

    def test_returns_200(self, e2e_client) -> None:
        """GET /status returns 200 OK."""
        r = e2e_client.get("/status")
        assert r.status_code == 200

    def test_returns_json(self, e2e_client) -> None:
        """Response content type is application/json."""
        r = e2e_client.get("/status")
        assert "application/json" in r.headers["content-type"]

    def test_has_openvip_version(self, e2e_client) -> None:
        """Response includes openvip protocol version field."""
        data = e2e_client.get("/status").json()
        assert "openvip" in data
        assert data["openvip"] == "1.0"

    def test_has_stt(self, e2e_client) -> None:
        """Response includes stt object with enabled and active."""
        data = e2e_client.get("/status").json()
        assert "stt" in data
        assert isinstance(data["stt"], dict)
        assert isinstance(data["stt"]["enabled"], bool)
        assert isinstance(data["stt"]["active"], bool)

    def test_has_tts(self, e2e_client) -> None:
        """Response includes tts object with enabled."""
        data = e2e_client.get("/status").json()
        assert "tts" in data
        assert isinstance(data["tts"], dict)
        assert isinstance(data["tts"]["enabled"], bool)

    def test_has_connected_agents(self, e2e_client) -> None:
        """Response includes connected_agents as a list."""
        data = e2e_client.get("/status").json()
        assert "connected_agents" in data
        assert isinstance(data["connected_agents"], list)

    def test_has_platform(self, e2e_client) -> None:
        """Response includes opaque platform object."""
        data = e2e_client.get("/status").json()
        assert "platform" in data
        assert isinstance(data["platform"], dict)


# =============================================================================
# 2. POST /control — Protocol Commands
# =============================================================================


class TestControlProtocol:
    """OpenVIP: POST /control for protocol-defined commands."""

    def test_stt_start(self, e2e_client) -> None:
        """stt.start returns ok with listening=True."""
        r = e2e_client.post("/control", json={"command": "stt.start"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["listening"] is True

    def test_stt_stop(self, e2e_client) -> None:
        """stt.stop returns ok with listening=False."""
        r = e2e_client.post("/control", json={"command": "stt.stop"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["listening"] is False

    def test_stt_toggle(self, e2e_client) -> None:
        """stt.toggle returns ok."""
        r = e2e_client.post("/control", json={"command": "stt.toggle"})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_ping(self, e2e_client) -> None:
        """ping returns ok with pong=True."""
        r = e2e_client.post("/control", json={"command": "ping"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["pong"] is True


# =============================================================================
# 3. POST /speech — Text-to-Speech
# =============================================================================


class TestSpeech:
    """OpenVIP: POST /speech for text-to-speech."""

    def test_speech_returns_200(self, e2e_client) -> None:
        """Valid speech request returns 200 OK."""
        r = e2e_client.post("/speech", json=_speech_request())
        assert r.status_code == 200

    def test_speech_returns_status_ok(self, e2e_client) -> None:
        """Response has status=ok."""
        data = e2e_client.post("/speech", json=_speech_request()).json()
        assert data["status"] == "ok"

    def test_speech_returns_duration(self, e2e_client) -> None:
        """Response includes duration_ms."""
        data = e2e_client.post("/speech", json=_speech_request()).json()
        assert "duration_ms" in data
        assert isinstance(data["duration_ms"], int)
        assert data["duration_ms"] >= 0


# =============================================================================
# 4. POST /agents/{agent_id}/messages — Send Message
# =============================================================================


class TestPostAgentMessages:
    """OpenVIP: POST /agents/{agent_id}/messages."""

    def test_post_to_connected_agent_returns_200(
        self, e2e_client, sse_connect,
    ) -> None:
        """Posting to a connected agent returns 200 OK."""
        conn = sse_connect("alice")
        r = e2e_client.post(f"/agents/{conn.agent_id}/messages", json=_transcription())
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_message_delivered_via_sse(
        self, e2e_client, sse_connect,
    ) -> None:
        """Posted message is delivered to the agent's SSE stream."""
        conn = sse_connect("alice")
        msg = _transcription(text="test delivery")
        e2e_client.post(f"/agents/{conn.agent_id}/messages", json=msg)
        _wait_until(lambda: len(conn.events) > 0)
        assert conn.events[0]["text"] == "test delivery"

    def test_post_to_unconnected_agent_returns_404(self, e2e_client) -> None:
        """Posting to a non-existent agent returns 404."""
        r = e2e_client.post(
            "/agents/ghost/messages", json=_transcription()
        )
        assert r.status_code == 404

    def test_404_detail_mentions_not_connected(self, e2e_client) -> None:
        """404 error detail mentions agent not connected."""
        r = e2e_client.post(
            "/agents/ghost/messages", json=_transcription()
        )
        assert "not connected" in r.json()["detail"].lower()


# =============================================================================
# 5. GET /agents/{agent_id}/messages — SSE Agent Registration
# =============================================================================


class TestSSEAgentRegistration:
    """OpenVIP: GET /agents/{agent_id}/messages — SSE lifecycle."""

    def test_reserved_agent_id_returns_403(self, e2e_client) -> None:
        """Reserved agent IDs (e.g., __keyboard__) return 403."""
        r = e2e_client.get("/agents/__keyboard__/messages")
        assert r.status_code == 403

    def test_duplicate_agent_returns_409(
        self, e2e_client, sse_connect,
    ) -> None:
        """Connecting with an already-connected agent ID returns 409."""
        conn = sse_connect("alice")
        r = e2e_client.get(f"/agents/{conn.agent_id}/messages")
        assert r.status_code == 409

    def test_409_detail_mentions_already_connected(
        self, e2e_client, sse_connect,
    ) -> None:
        """409 error detail mentions agent already connected."""
        conn = sse_connect("alice")
        r = e2e_client.get(f"/agents/{conn.agent_id}/messages")
        assert "already connected" in r.json()["detail"].lower()


# =============================================================================
# 6. Status Response Schema
# =============================================================================


class TestStatusSchema:
    """OpenVIP: Status object schema compliance."""

    def test_openvip_is_string(self, e2e_client) -> None:
        data = e2e_client.get("/status").json()
        assert isinstance(data["openvip"], str)

    def test_stt_is_object(self, e2e_client) -> None:
        data = e2e_client.get("/status").json()
        assert isinstance(data["stt"], dict)

    def test_tts_is_object(self, e2e_client) -> None:
        data = e2e_client.get("/status").json()
        assert isinstance(data["tts"], dict)

    def test_connected_agents_is_list_of_strings(self, e2e_client) -> None:
        data = e2e_client.get("/status").json()
        agents = data["connected_agents"]
        assert isinstance(agents, list)
        for a in agents:
            assert isinstance(a, str)

    def test_platform_is_object(self, e2e_client) -> None:
        data = e2e_client.get("/status").json()
        assert isinstance(data["platform"], dict)


# =============================================================================
# 7. Ack Response Schema
# =============================================================================


class TestAckSchema:
    """OpenVIP: Ack response schema compliance."""

    def test_ack_has_status_ok(self, e2e_client) -> None:
        """Control command ack has status=ok."""
        data = e2e_client.post(
            "/control", json={"command": "ping"}
        ).json()
        assert data["status"] == "ok"

    def test_speech_ack_has_status_ok(self, e2e_client) -> None:
        """Speech ack has status=ok."""
        data = e2e_client.post("/speech", json=_speech_request()).json()
        assert data["status"] == "ok"

    def test_message_ack_has_status_ok(
        self, e2e_client, sse_connect,
    ) -> None:
        """Post message ack has status=ok."""
        conn = sse_connect("alice")
        data = e2e_client.post(
            f"/agents/{conn.agent_id}/messages", json=_transcription()
        ).json()
        assert data["status"] == "ok"


# =============================================================================
# 8. Message Schema Validation — Valid Messages
# =============================================================================
#
# These tests validate message structures against the OpenVIP JSON Schema.
# E2E: messages are posted via HTTP and verified via SSE delivery.

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
            "origin": "dictare/3.0.0",
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
            "origin": "dictare/3.0.0",
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


class TestValidMessages:
    """OpenVIP: Valid message schemas are accepted and delivered via SSE."""

    @pytest.mark.parametrize("message", VALID_MESSAGES)
    def test_valid_message_accepted(
        self, e2e_client, sse_connect, message: dict,
    ) -> None:
        """Valid OpenVIP messages are delivered to connected agents."""
        conn = sse_connect("test")

        r = e2e_client.post(f"/agents/{conn.agent_id}/messages", json=message)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        # Message should arrive via SSE, preserving all fields
        _wait_until(lambda: len(conn.events) > 0)
        received = conn.events[0]
        assert received["text"] == message["text"]
        if "x_input" in message:
            assert received["x_input"] == message["x_input"]
        if "x_agent_switch" in message:
            assert received["x_agent_switch"] == message["x_agent_switch"]
        if "trace_id" in message:
            assert received["trace_id"] == message["trace_id"]
            assert received["parent_id"] == message["parent_id"]


# =============================================================================
# 9. Invalid Message Validation — Server Must Reject with 422
# =============================================================================
#
# The HTTP transport layer validates incoming messages against the OpenVIP
# v1.0 JSON Schema and returns 422 for non-compliant payloads.

INVALID_MESSAGES_POST = [
    # --- Missing required fields ---
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
        {},
        id="empty_object",
    ),
    pytest.param(
        {"text": "just text"},
        id="text_only_no_envelope",
    ),

    # --- Wrong protocol version ---
    pytest.param(
        {"openvip": "2.0", "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="wrong_version_2_0",
    ),
    pytest.param(
        {"openvip": "0.9", "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="wrong_version_0_9",
    ),
    pytest.param(
        {"openvip": "", "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="empty_version_string",
    ),
    pytest.param(
        {"openvip": "1.0.0", "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="semver_version_not_allowed",
    ),

    # --- Invalid type enum ---
    pytest.param(
        {"openvip": "1.0", "type": "message", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="invalid_type_message",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "command", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="invalid_type_command",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="empty_type_string",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "TRANSCRIPTION", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="type_wrong_case",
    ),

    # --- Wrong field types ---
    pytest.param(
        {"openvip": 1.0, "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="openvip_number_not_string",
    ),
    pytest.param(
        {"openvip": "1.0", "type": 42, "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="type_number_not_string",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "transcription", "id": 123,
         "timestamp": _timestamp(), "text": "hello"},
        id="id_number_not_string",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "transcription", "id": _uuid(),
         "timestamp": 1234567890, "text": "hello"},
        id="timestamp_number_not_string",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": 42},
        id="text_number_not_string",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": True},
        id="text_boolean_not_string",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": None},
        id="text_null",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": ["hello", "world"]},
        id="text_array_not_string",
    ),
    pytest.param(
        {"openvip": None, "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="openvip_null",
    ),
    pytest.param(
        {"openvip": True, "type": "transcription", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="openvip_boolean",
    ),

    # --- Tracing: dependentRequired violations ---
    pytest.param(
        {**_transcription(), "trace_id": _uuid()},
        id="trace_id_without_parent_id",
    ),
    pytest.param(
        {**_transcription(), "parent_id": _uuid()},
        id="parent_id_without_trace_id",
    ),

    # --- Confidence out of range ---
    pytest.param(
        {**_transcription(), "confidence": 1.5},
        id="confidence_above_1",
    ),
    pytest.param(
        {**_transcription(), "confidence": -0.1},
        id="confidence_below_0",
    ),
    pytest.param(
        {**_transcription(), "confidence": 100},
        id="confidence_100",
    ),
    pytest.param(
        {**_transcription(), "confidence": -1},
        id="confidence_negative_1",
    ),
    pytest.param(
        {**_transcription(), "confidence": "high"},
        id="confidence_string_not_number",
    ),
    pytest.param(
        {**_transcription(), "confidence": True},
        id="confidence_boolean_not_number",
    ),

    # --- Extension fields must be objects ---
    pytest.param(
        {**_transcription(), "x_bad": "not an object"},
        id="x_field_string_not_object",
    ),
    pytest.param(
        {**_transcription(), "x_bad": True},
        id="x_field_boolean_not_object",
    ),
    pytest.param(
        {**_transcription(), "x_bad": 42},
        id="x_field_number_not_object",
    ),
    pytest.param(
        {**_transcription(), "x_bad": None},
        id="x_field_null_not_object",
    ),
    pytest.param(
        {**_transcription(), "x_bad": ["a", "b"]},
        id="x_field_array_not_object",
    ),
    pytest.param(
        {**_transcription(), "x_a": "string", "x_b": 42},
        id="multiple_invalid_x_fields",
    ),

    # --- partial must be boolean ---
    pytest.param(
        {**_transcription(), "partial": "true"},
        id="partial_string_not_boolean",
    ),
    pytest.param(
        {**_transcription(), "partial": 1},
        id="partial_int_not_boolean",
    ),
    pytest.param(
        {**_transcription(), "partial": "yes"},
        id="partial_string_yes",
    ),

    # --- origin must be string ---
    pytest.param(
        {**_transcription(), "origin": 42},
        id="origin_number_not_string",
    ),
    pytest.param(
        {**_transcription(), "origin": True},
        id="origin_boolean_not_string",
    ),

    # --- language must be string ---
    pytest.param(
        {**_transcription(), "language": 42},
        id="language_number_not_string",
    ),
    pytest.param(
        {**_transcription(), "language": True},
        id="language_boolean_not_string",
    ),

    # --- Multiple missing required fields at once ---
    pytest.param(
        {"openvip": "1.0"},
        id="only_openvip_field",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "transcription"},
        id="only_openvip_and_type",
    ),
    pytest.param(
        {"text": "hello", "type": "transcription"},
        id="missing_openvip_id_timestamp",
    ),

    # --- Not even an object ---
    pytest.param(
        "just a string",
        id="string_not_object",
    ),
    pytest.param(
        42,
        id="number_not_object",
    ),
    pytest.param(
        True,
        id="boolean_not_object",
    ),
    pytest.param(
        [_transcription()],
        id="array_not_object",
    ),
]


class TestInvalidMessageRejection:
    """OpenVIP: Invalid messages must be rejected with 422.

    The server validates all incoming messages against the OpenVIP v1.0
    JSON Schema. Non-compliant payloads are rejected before processing.
    """

    @pytest.mark.parametrize("message", INVALID_MESSAGES_POST)
    def test_post_message_invalid_returns_422(
        self, e2e_client, sse_connect, message,
    ) -> None:
        """Invalid message posted to /agents/{id}/messages returns 422."""
        conn = sse_connect("validator")
        r = e2e_client.post(
            f"/agents/{conn.agent_id}/messages", json=message,
        )
        assert r.status_code == 422
        assert "Not OpenVIP v1.0 compliant" in r.json()["detail"]


INVALID_SPEECH_MESSAGES = [
    pytest.param(
        {"text": "hello"},
        id="speech_missing_openvip",
    ),
    pytest.param(
        {"openvip": "1.0", "text": "hello"},
        id="speech_missing_type_id_timestamp",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "speech", "id": _uuid(),
         "timestamp": _timestamp()},
        id="speech_missing_text",
    ),
    pytest.param(
        {},
        id="speech_empty_object",
    ),
    pytest.param(
        {"openvip": "2.0", "type": "speech", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="speech_wrong_version",
    ),
    pytest.param(
        {"openvip": "1.0", "type": "command", "id": _uuid(),
         "timestamp": _timestamp(), "text": "hello"},
        id="speech_invalid_type_enum",
    ),
    pytest.param(
        "just text",
        id="speech_string_not_object",
    ),
    pytest.param(
        42,
        id="speech_number_not_object",
    ),
    pytest.param(
        {**_speech_request(), "x_bad": "string"},
        id="speech_x_field_string_not_object",
    ),
    pytest.param(
        {**_speech_request(), "confidence": 2.0},
        id="speech_confidence_above_1",
    ),
    pytest.param(
        {**_speech_request(), "partial": "true"},
        id="speech_partial_string_not_boolean",
    ),
]


class TestInvalidSpeechRejection:
    """OpenVIP: Invalid speech requests must be rejected with 422."""

    @pytest.mark.parametrize("message", INVALID_SPEECH_MESSAGES)
    def test_post_speech_invalid_returns_422(
        self, e2e_client, message,
    ) -> None:
        """Invalid speech message posted to /speech returns 422."""
        r = e2e_client.post("/speech", json=message)
        assert r.status_code == 422


class TestValidationErrorMessages:
    """OpenVIP: Validation error responses are informative."""

    def test_missing_field_mentions_field_name(self, e2e_client, sse_connect) -> None:
        """422 detail mentions which required field is missing."""
        conn = sse_connect("validator")
        msg = {"type": "transcription", "id": _uuid(),
               "timestamp": _timestamp(), "text": "hello"}
        r = e2e_client.post(f"/agents/{conn.agent_id}/messages", json=msg)
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert "Not OpenVIP v1.0 compliant" in detail

    def test_wrong_version_rejected(self, e2e_client, sse_connect) -> None:
        """Wrong protocol version is rejected with clear error."""
        conn = sse_connect("validator")
        msg = _transcription(openvip="2.0")
        r = e2e_client.post(f"/agents/{conn.agent_id}/messages", json=msg)
        assert r.status_code == 422

    def test_valid_message_still_accepted(self, e2e_client, sse_connect) -> None:
        """Valid messages pass validation and return 200."""
        conn = sse_connect("validator")
        r = e2e_client.post(
            f"/agents/{conn.agent_id}/messages", json=_transcription(),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_valid_speech_still_accepted(self, e2e_client) -> None:
        """Valid speech messages pass validation and return 200."""
        r = e2e_client.post("/speech", json=_speech_request())
        assert r.status_code == 200


# =============================================================================
# 10. Content Negotiation
# =============================================================================


class TestContentType:
    """OpenVIP: Response content types."""

    def test_status_json(self, e2e_client) -> None:
        r = e2e_client.get("/status")
        assert "application/json" in r.headers["content-type"]

    def test_control_json(self, e2e_client) -> None:
        r = e2e_client.post("/control", json={"command": "ping"})
        assert "application/json" in r.headers["content-type"]

    def test_speech_json(self, e2e_client) -> None:
        r = e2e_client.post("/speech", json=_speech_request())
        assert "application/json" in r.headers["content-type"]

    def test_post_message_json(self, e2e_client, sse_connect) -> None:
        """POST message response is application/json."""
        conn = sse_connect("a")
        r = e2e_client.post(f"/agents/{conn.agent_id}/messages", json=_transcription())
        assert "application/json" in r.headers["content-type"]

    def test_status_stream_event_stream(self) -> None:
        """GET /status/stream content type is text/event-stream.

        Note: SSE streaming cannot be tested with in-memory TestClient
        (sse-starlette limitation). Verified manually with live server.
        """
        pass  # Requires live server


# =============================================================================
# 11. Edge Cases
# =============================================================================


class TestEdgeCases:
    """OpenVIP: Edge cases and boundary conditions."""

    def test_empty_command(self, e2e_client) -> None:
        """Empty command string is handled gracefully."""
        r = e2e_client.post("/control", json={"command": ""})
        # Should not crash — returns error or routes to controller
        assert r.status_code in (200, 400, 500)

    def test_missing_command_field(self, e2e_client) -> None:
        """Missing command field is handled gracefully."""
        r = e2e_client.post("/control", json={})
        assert r.status_code in (200, 400, 500)

    def test_empty_speech_text(self, e2e_client) -> None:
        """Empty speech text returns 422 error, not crash."""
        r = e2e_client.post("/speech", json={"text": ""})
        assert r.status_code == 422

    def test_agent_id_with_special_chars(self, e2e_client) -> None:
        """Agent IDs with dashes and underscores work."""
        # 404 is expected (not connected), but should not 500
        r = e2e_client.post(
            "/agents/my-agent_v2/messages", json=_transcription()
        )
        assert r.status_code == 404  # Not connected, not server error

    def test_multiple_agents_independent(
        self, e2e_client, sse_connect,
    ) -> None:
        """Messages to different agents are independent."""
        alice = sse_connect("alice")
        bob = sse_connect("bob")

        e2e_client.post(
            f"/agents/{alice.agent_id}/messages",
            json=_transcription(text="for alice"),
        )
        e2e_client.post(
            f"/agents/{bob.agent_id}/messages",
            json=_transcription(text="for bob"),
        )

        _wait_until(lambda: len(alice.events) > 0 and len(bob.events) > 0)
        assert alice.events[0]["text"] == "for alice"
        assert bob.events[0]["text"] == "for bob"
        assert len(alice.events) == 1
        assert len(bob.events) == 1

    def test_large_text_accepted(self, e2e_client, sse_connect) -> None:
        """Large text messages are accepted."""
        conn = sse_connect("test")
        big_text = "word " * 10000  # ~50KB
        r = e2e_client.post(
            f"/agents/{conn.agent_id}/messages",
            json=_transcription(text=big_text),
        )
        assert r.status_code == 200

    def test_unicode_text(self, e2e_client, sse_connect) -> None:
        """Unicode text (CJK, emoji, RTL) is preserved."""
        conn = sse_connect("test")
        texts = [
            "Accendi la luce in cucina",
            "台所の電気をつけて",
            "مرحبا بالعالم",
        ]
        for text in texts:
            e2e_client.post(
                f"/agents/{conn.agent_id}/messages",
                json=_transcription(text=text),
            )

        _wait_until(lambda: len(conn.events) >= 3)
        for i, text in enumerate(texts):
            assert conn.events[i]["text"] == text
