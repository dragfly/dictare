"""Tests for TTS worker proxy and token bypass."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dictare.core.http_server import OpenVIPServer
from dictare.tts.proxy import WorkerTTSEngine

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

class _MockTTSMgr:
    """Minimal mock TTSManager for proxy access."""

    def __init__(self) -> None:
        self._tts_proxy: WorkerTTSEngine | None = None

    def complete_tts(self, message_id: str, *, ok: bool, duration_ms: int = 0) -> None:
        if self._tts_proxy is not None:
            self._tts_proxy.complete(message_id, ok=ok, duration_ms=duration_ms)

class MockEngine:
    """Minimal mock engine for TTS worker tests."""

    RESERVED_AGENT_IDS = {"__keyboard__", "__tts__"}
    TTS_AGENT_ID = "__tts__"

    def __init__(self) -> None:
        self._registered_agents: list = []
        self._unregistered_agents: list[str] = []
        self._tts_mgr = _MockTTSMgr()

    def register_agent(self, agent) -> bool:
        self._registered_agents.append(agent)
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        self._unregistered_agents.append(agent_id)
        return True

    def get_status(self) -> dict:
        return {"protocol_version": "1.0", "state": "idle", "connected_agents": []}

    def complete_tts(self, message_id: str, *, ok: bool, duration_ms: int = 0) -> None:
        self._tts_mgr.complete_tts(message_id, ok=ok, duration_ms=duration_ms)

@pytest.fixture
def engine() -> MockEngine:
    return MockEngine()

@pytest.fixture
def token() -> str:
    return "test-token-abc123"

@pytest.fixture
def server(engine: MockEngine, token: str) -> OpenVIPServer:
    return OpenVIPServer(
        engine, None,
        host="127.0.0.1", port=0,
        auth_tokens={"register_tts": token},
    )

@pytest.fixture
def client(server: OpenVIPServer) -> TestClient:
    return TestClient(server._app)

# ---------------------------------------------------------------------------
# Part 2: Token bypass tests
# ---------------------------------------------------------------------------

class TestReservedAgentBypass:
    """Token bypass for reserved agent IDs.

    Note: SSE (GET) endpoints block in TestClient, so we test POST instead
    for the "accepted" path and use a direct HTTP client for the rejection
    path which returns immediately (403).
    """

    def test_reserved_agent_rejected_without_token(
        self, client: TestClient,
    ) -> None:
        """GET /agents/__tts__/messages without token → 403."""
        # 403 responses are returned immediately (no SSE stream)
        response = client.get("/agents/__tts__/messages")
        assert response.status_code == 403
        assert "Reserved" in response.json()["detail"]

    def test_reserved_agent_rejected_with_wrong_token(
        self, client: TestClient,
    ) -> None:
        """GET /agents/__tts__/messages with wrong token → 403."""
        response = client.get(
            "/agents/__tts__/messages",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 403

    def test_keyboard_agent_rejected_without_token(
        self, client: TestClient,
    ) -> None:
        """GET /agents/__keyboard__/messages without token → 403."""
        response = client.get("/agents/__keyboard__/messages")
        assert response.status_code == 403

class TestTTSCompleteEndpoint:
    """POST /internal/tts/complete endpoint."""

    def test_complete_without_token_rejected(
        self, client: TestClient,
    ) -> None:
        """POST /internal/tts/complete without token → 403."""
        response = client.post(
            "/internal/tts/complete",
            json={"message_id": "abc", "ok": True},
        )
        assert response.status_code == 403

    def test_complete_with_token_succeeds(
        self, client: TestClient, token: str,
    ) -> None:
        """POST /internal/tts/complete with valid token → 200."""
        response = client.post(
            "/internal/tts/complete",
            json={"message_id": "abc", "ok": True, "duration_ms": 100},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_complete_calls_proxy(
        self, client: TestClient, engine: MockEngine, token: str,
    ) -> None:
        """POST /internal/tts/complete triggers proxy.complete()."""
        proxy = MagicMock()
        engine._tts_mgr._tts_proxy = proxy

        client.post(
            "/internal/tts/complete",
            json={"message_id": "req-1", "ok": True, "duration_ms": 250},
            headers={"Authorization": f"Bearer {token}"},
        )

        proxy.complete.assert_called_once_with(
            "req-1", ok=True, duration_ms=250,
        )

class TestTTSConnectedEvent:
    """_tts_connected_event lifecycle."""

    def test_initially_not_set(self, server: OpenVIPServer) -> None:
        """TTS connected event is not set initially."""
        assert not server._tts_connected_event.is_set()

# ---------------------------------------------------------------------------
# Part 3: WorkerTTSEngine proxy tests
# ---------------------------------------------------------------------------

class TestWorkerTTSEngine:
    """WorkerTTSEngine proxy unit tests."""

    def test_get_name(self, server: OpenVIPServer) -> None:
        proxy = WorkerTTSEngine(server)
        assert proxy.get_name() == "worker"

    def test_is_available_false_when_not_connected(
        self, server: OpenVIPServer,
    ) -> None:
        proxy = WorkerTTSEngine(server)
        assert proxy.is_available() is False

    def test_is_available_true_when_connected(
        self, server: OpenVIPServer,
    ) -> None:
        server._tts_connected_event.set()
        proxy = WorkerTTSEngine(server)
        assert proxy.is_available() is True

    def test_speak_returns_false_when_worker_not_connected(
        self, server: OpenVIPServer,
    ) -> None:
        """speak() returns False immediately if worker not connected."""
        proxy = WorkerTTSEngine(server)
        result = proxy.speak("hello")
        assert result is False

    def test_complete_sets_result(self, server: OpenVIPServer) -> None:
        """complete() unblocks pending speak() with correct result."""
        proxy = WorkerTTSEngine(server)

        # Simulate a pending request
        done = threading.Event()
        result = {"ok": False}
        proxy._pending["req-1"] = (done, result)

        proxy.complete("req-1", ok=True, duration_ms=500)

        assert done.is_set()
        assert result["ok"] is True
        assert result["duration_ms"] == 500

    def test_complete_unknown_request_is_noop(
        self, server: OpenVIPServer,
    ) -> None:
        """complete() for unknown message_id does not raise."""
        proxy = WorkerTTSEngine(server)
        proxy.complete("nonexistent", ok=True)  # Should not raise

    def test_speak_with_worker_connected(
        self, server: OpenVIPServer,
    ) -> None:
        """speak() delivers message and waits for completion."""
        import dictare.tts.proxy as proxy_mod

        # Use a short timeout for tests
        original_timeout = proxy_mod._SPEAK_TIMEOUT
        proxy_mod._SPEAK_TIMEOUT = 5.0

        try:
            # Simulate a connected worker by creating a queue
            queue: asyncio.Queue = asyncio.Queue()
            with server._agent_queues_lock:
                server._agent_queues["__tts__"] = queue

            # We need a running event loop for put_message to work
            loop = asyncio.new_event_loop()
            server._loop = loop

            def run_loop():
                asyncio.set_event_loop(loop)
                loop.run_forever()

            loop_thread = threading.Thread(target=run_loop, daemon=True)
            loop_thread.start()

            proxy = WorkerTTSEngine(server)

            # Complete the request from another thread (simulating worker)
            def complete_after_delivery():
                import time
                time.sleep(0.1)
                for req_id in list(proxy._pending.keys()):
                    proxy.complete(req_id, ok=True, duration_ms=100)

            completer = threading.Thread(
                target=complete_after_delivery, daemon=True,
            )
            completer.start()

            result = proxy.speak("hello")
            assert result is True

            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2)
            loop.close()
        finally:
            proxy_mod._SPEAK_TIMEOUT = original_timeout

# ---------------------------------------------------------------------------
# Has-permission helper
# ---------------------------------------------------------------------------

class TestHasPermission:
    """_has_permission helper method."""

    def test_no_token_configured(self, engine: MockEngine) -> None:
        """Returns False if no token is configured for the permission."""
        server = OpenVIPServer(engine, None, auth_tokens={})
        request = MagicMock()
        request.headers = {"authorization": "Bearer something"}
        assert server._has_permission(request, "register_tts") is False

    def test_correct_token(self, server: OpenVIPServer, token: str) -> None:
        request = MagicMock()
        request.headers = {"authorization": f"Bearer {token}"}
        assert server._has_permission(request, "register_tts") is True

    def test_wrong_token(self, server: OpenVIPServer) -> None:
        request = MagicMock()
        request.headers = {"authorization": "Bearer wrong"}
        assert server._has_permission(request, "register_tts") is False

    def test_missing_header(self, server: OpenVIPServer) -> None:
        request = MagicMock()
        request.headers = {}
        assert server._has_permission(request, "register_tts") is False
