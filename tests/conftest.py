"""Shared pytest configuration, hooks, and compliance test infrastructure."""

from __future__ import annotations

import pytest

from dictare.core.http_server import OpenVIPServer

# =============================================================================
# Pytest hooks
# =============================================================================

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--openvip-url",
        default=None,
        help="URL of a running OpenVIP server to test against (e.g. http://localhost:8770)",
    )
    parser.addoption(
        "--openvip-timeout-factor",
        default=1.0,
        type=float,
        help="Multiply all wait timeouts by this factor (default: 1.0). "
        "Use higher values for slow implementations (e.g. 5.0).",
    )

def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Auto-skip @pytest.mark.internal tests when --openvip-url is set."""
    url = config.getoption("--openvip-url")
    if url is None:
        return
    skip = pytest.mark.skip(reason=f"internal test, skipped with --openvip-url={url}")
    for item in items:
        if "internal" in item.keywords:
            item.add_marker(skip)

# =============================================================================
# Compliance mock implementations
# =============================================================================

class ComplianceMockEngine:
    """Minimal mock engine implementing the public API surface.

    Used by both protocol tests (via live_url fixture) and internal tests
    (via engine/server fixtures).
    """

    RESERVED_AGENT_IDS = {"__keyboard__"}

    def __init__(self) -> None:
        self._registered: list = []
        self._unregistered: list[str] = []
        self._speech_calls: list[dict] = []
        self._protocol_calls: list[dict] = []
        self._state = "off"

    def register_agent(self, agent) -> bool:
        self._registered.append(agent)
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        self._unregistered.append(agent_id)
        return True

    def get_status(self) -> dict:
        stt_active = self._state in ("listening", "recording", "transcribing")
        return {
            "openvip": "1.0",
            "stt": {"enabled": True, "active": stt_active},
            "tts": {"enabled": True},
            "connected_agents": [],
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
            self._state = "off"
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

# =============================================================================
# Shared fixtures
# =============================================================================

@pytest.fixture
def engine() -> ComplianceMockEngine:
    return ComplianceMockEngine()

@pytest.fixture
def controller() -> ComplianceMockController:
    return ComplianceMockController()

@pytest.fixture
def server(engine, controller) -> OpenVIPServer:
    return OpenVIPServer(engine, controller, host="127.0.0.1", port=0)

@pytest.fixture(scope="module")
def live_url(request):
    """URL of a running OpenVIP server (module-scoped).

    Uses --openvip-url if provided, otherwise starts an embedded server.
    Module-scoped: one server start/stop per test module.
    """
    url = request.config.getoption("--openvip-url")
    if url:
        yield url
    else:
        mock_engine = ComplianceMockEngine()
        mock_controller = ComplianceMockController()
        srv = OpenVIPServer(
            mock_engine, mock_controller, host="127.0.0.1", port=0,
        )
        srv.start()
        assert srv.wait_started(timeout=5.0), "Server did not start"
        yield f"http://127.0.0.1:{srv.port}"
        srv.stop()
