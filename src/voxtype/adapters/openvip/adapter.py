"""OpenVIP Adapter - exposes VoxtypeEngine via OpenVIP protocol.

The adapter:
- Wraps a VoxtypeEngine instance
- Subscribes to engine events (Python callbacks)
- Translates events to OpenVIP messages
- Exposes HTTP and Unix socket endpoints
- Handles OpenVIP control commands

Usage:
    from voxtype.core.engine import VoxtypeEngine
    from voxtype.adapters.openvip import OpenVIPAdapter

    engine = VoxtypeEngine(config, events)
    adapter = OpenVIPAdapter(engine, config)
    adapter.start()  # Starts HTTP + socket servers
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from voxtype import __version__

if TYPE_CHECKING:
    from voxtype.config import Config
    from voxtype.core.engine import VoxtypeEngine

logger = logging.getLogger(__name__)


def get_voxtype_dir() -> Path:
    """Get the voxtype data directory (~/.voxtype)."""
    return Path.home() / ".voxtype"


def get_socket_path() -> Path:
    """Get the adapter socket path."""
    return get_voxtype_dir() / "engine.sock"


def get_pid_path() -> Path:
    """Get the adapter PID file path."""
    return get_voxtype_dir() / "engine.pid"


# =============================================================================
# State dataclasses (for /status endpoint)
# =============================================================================


@dataclass
class STTState:
    """STT service state."""

    state: str = "idle"  # idle, listening, recording, transcribing
    model_loaded: bool = False
    model_name: str | None = None
    language: str | None = None


@dataclass
class OutputState:
    """Output configuration state."""

    mode: str = "keyboard"
    current_agent: str | None = None
    available_agents: list[str] = field(default_factory=list)


@dataclass
class HotkeyState:
    """Hotkey state."""

    bound: bool = False
    key: str = ""


@dataclass
class LoadingProgress:
    """Model loading progress."""

    name: str = ""
    status: str = "pending"  # pending, loading, done, error
    elapsed: float = 0.0
    estimated: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dict for JSON."""
        progress = 0.0
        if self.status == "done":
            progress = 1.0
        elif self.status == "loading" and self.estimated > 0:
            progress = min(self.elapsed / self.estimated, 0.99)
        return {
            "name": self.name,
            "status": self.status,
            "progress": progress,
            "elapsed": self.elapsed,
            "estimated": self.estimated,
            "error": None,
        }


@dataclass
class LoadingState:
    """Loading state for /status."""

    active: bool = False
    models: list[LoadingProgress] = field(default_factory=list)


@dataclass
class AdapterState:
    """Full adapter state exposed via /status."""

    stt: STTState = field(default_factory=STTState)
    output: OutputState = field(default_factory=OutputState)
    hotkey: HotkeyState = field(default_factory=HotkeyState)
    loading: LoadingState = field(default_factory=LoadingState)
    version: str = __version__
    pid: int = 0
    uptime_seconds: float = 0.0
    mode: str = "foreground"
    started_at: str = ""

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "stt": {
                "state": self.stt.state,
                "model_loaded": self.stt.model_loaded,
                "model_name": self.stt.model_name,
                "language": self.stt.language,
            },
            "output": {
                "mode": self.output.mode,
                "current_agent": self.output.current_agent,
                "available_agents": self.output.available_agents,
            },
            "hotkey": {
                "bound": self.hotkey.bound,
                "key": self.hotkey.key,
            },
            "loading": {
                "active": self.loading.active,
                "models": [m.to_dict() for m in self.loading.models],
            },
            "engine": {
                "version": self.version,
                "pid": self.pid,
                "uptime_seconds": self.uptime_seconds,
                "mode": self.mode,
                "started_at": self.started_at,
            },
        }


# =============================================================================
# Control Handler
# =============================================================================


@dataclass
class ControlResponse:
    """Response to a control command."""

    status: str  # "ok" or "error"
    error_code: str | None = None
    error_message: str | None = None


class ControlHandler:
    """Handles OpenVIP control commands."""

    def __init__(self, adapter: OpenVIPAdapter) -> None:
        self._adapter = adapter
        self._handlers: dict[str, Any] = {
            "stt.start": self._handle_stt_start,
            "stt.stop": self._handle_stt_stop,
            "output.set_agent": self._handle_output_set_agent,
            "hotkey.bind": self._handle_hotkey_bind,
            "hotkey.unbind": self._handle_hotkey_unbind,
            "engine.shutdown": self._handle_engine_shutdown,
            "ping": self._handle_ping,
        }

    def handle_command(self, message: dict) -> dict:
        """Handle an OpenVIP control command."""
        command = message.get("command", "")
        msg_id = message.get("id", str(uuid4()))
        payload = message.get("payload", {})

        handler = self._handlers.get(command)
        if not handler:
            return self._create_response(
                msg_id,
                ControlResponse(
                    status="error",
                    error_code="INVALID_COMMAND",
                    error_message=f"Unknown command: {command}",
                ),
            )

        try:
            result = handler(payload)
            return self._create_response(msg_id, result)
        except Exception as e:
            logger.exception(f"Error handling command {command}")
            return self._create_response(
                msg_id,
                ControlResponse(
                    status="error",
                    error_code="INTERNAL_ERROR",
                    error_message=str(e),
                ),
            )

    def _create_response(self, msg_id: str, result: ControlResponse) -> dict:
        response: dict[str, Any] = {
            "openvip": "1.0",
            "type": "control.response",
            "id": msg_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": result.status,
        }
        if result.error_code:
            response["error"] = {
                "code": result.error_code,
                "message": result.error_message,
            }
        return response

    def _handle_stt_start(self, payload: dict) -> ControlResponse:
        engine = self._adapter._engine
        if engine and engine.is_listening:
            return ControlResponse(status="ok")
        if engine:
            engine._set_listening(True)
        return ControlResponse(status="ok")

    def _handle_stt_stop(self, payload: dict) -> ControlResponse:
        engine = self._adapter._engine
        if engine:
            engine._set_listening(False)
        return ControlResponse(status="ok")

    def _handle_output_set_agent(self, payload: dict) -> ControlResponse:
        agent = payload.get("agent")
        if not agent:
            return ControlResponse(
                status="error",
                error_code="INVALID_PAYLOAD",
                error_message="agent is required",
            )
        if agent not in self._adapter.state.output.available_agents:
            return ControlResponse(
                status="error",
                error_code="AGENT_NOT_FOUND",
                error_message=f"Agent not found: {agent}",
            )
        self._adapter.state.output.current_agent = agent
        return ControlResponse(status="ok")

    def _handle_hotkey_bind(self, payload: dict) -> ControlResponse:
        self._adapter.state.hotkey.bound = True
        return ControlResponse(status="ok")

    def _handle_hotkey_unbind(self, payload: dict) -> ControlResponse:
        self._adapter.state.hotkey.bound = False
        return ControlResponse(status="ok")

    def _handle_engine_shutdown(self, payload: dict) -> ControlResponse:
        self._adapter.request_shutdown()
        return ControlResponse(status="ok")

    def _handle_ping(self, payload: dict) -> ControlResponse:
        return ControlResponse(status="ok")


# =============================================================================
# HTTP Server
# =============================================================================


class AdapterHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for adapter endpoints."""

    adapter: OpenVIPAdapter

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code: str, message: str, status: int = 400) -> None:
        self._send_json({"error": {"code": code, "message": message}}, status)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/status":
            self._send_json(self.adapter.get_status())
        elif self.path == "/events":
            self._handle_events()
        else:
            self._send_error("NOT_FOUND", f"Unknown endpoint: {self.path}", 404)

    def do_POST(self) -> None:
        if self.path == "/control":
            self._handle_control()
        else:
            self._send_error("NOT_FOUND", f"Unknown endpoint: {self.path}", 404)

    def _handle_control(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            message = json.loads(body)
        except json.JSONDecodeError as e:
            self._send_error("INVALID_JSON", str(e))
            return

        if message.get("openvip") != "1.0":
            self._send_error("INVALID_PROTOCOL", "openvip must be '1.0'")
            return
        if message.get("type") != "control":
            self._send_error("INVALID_TYPE", "type must be 'control'")
            return

        response = self.adapter.handle_control(message)
        status_code = 200 if response.get("status") == "ok" else 400
        self._send_json(response, status_code)

    def _handle_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        event_queue: Queue[dict | None] = Queue()
        self.adapter.register_event_listener(event_queue)

        try:
            while True:
                event = event_queue.get()
                if event is None:
                    break
                data = json.dumps(event)
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.adapter.unregister_event_listener(event_queue)


# =============================================================================
# Unix Socket Server
# =============================================================================


class UnixSocketServer:
    """Unix socket server for adapter API."""

    def __init__(self, adapter: OpenVIPAdapter, socket_path: Path) -> None:
        self._adapter = adapter
        self._socket_path = socket_path
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._socket_path.exists():
            self._socket_path.unlink()
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)

        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self._socket_path))
        self._server.listen(5)
        self._server.settimeout(1.0)

        self._running = True
        self._thread = threading.Thread(target=self._serve_loop, daemon=True)
        self._thread.start()
        logger.info(f"Unix socket server started on {self._socket_path}")

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        if self._socket_path.exists():
            try:
                self._socket_path.unlink()
            except Exception:
                pass

    def _serve_loop(self) -> None:
        while self._running and self._server:
            try:
                conn, _ = self._server.accept()
                threading.Thread(
                    target=self._handle_connection, args=(conn,), daemon=True
                ).start()
            except TimeoutError:
                continue
            except OSError:
                break

    def _handle_connection(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(30)
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            if not data:
                return

            request = json.loads(data.decode("utf-8").strip())
            endpoint = request.get("endpoint", "")
            body = request.get("body", {})

            if endpoint == "/status":
                result = self._adapter.get_status()
                response = {"status": 200, "body": result}
            elif endpoint == "/control":
                if body.get("openvip") != "1.0":
                    response = {"status": 400, "error": "openvip must be '1.0'"}
                elif body.get("type") != "control":
                    response = {"status": 400, "error": "type must be 'control'"}
                else:
                    result = self._adapter.handle_control(body)
                    status = 200 if result.get("status") == "ok" else 400
                    response = {"status": status, "body": result}
            else:
                response = {"status": 404, "error": f"Unknown endpoint: {endpoint}"}

            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

        except Exception as e:
            logger.debug(f"Socket connection error: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass


# =============================================================================
# OpenVIPAdapter
# =============================================================================


class OpenVIPAdapter:
    """OpenVIP Adapter - exposes VoxtypeEngine via OpenVIP protocol.

    Usage:
        adapter = OpenVIPAdapter(engine, config)
        adapter.start()  # Starts HTTP + socket servers, loads models
        adapter.run()    # Blocks until shutdown
    """

    def __init__(self, engine: VoxtypeEngine, config: Config) -> None:
        """Initialize the adapter.

        Args:
            engine: VoxtypeEngine instance to wrap.
            config: Application configuration.
        """
        self._engine = engine
        self._config = config
        self._running = False
        self._shutdown_requested = False
        self._start_time: float = 0

        # State
        self.state = AdapterState()

        # Control handler
        self._control = ControlHandler(self)

        # Transport
        self._http_server: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._socket_server: UnixSocketServer | None = None

        # Event listeners (for SSE)
        self._event_listeners: list[Queue[dict | None]] = []
        self._event_lock = threading.Lock()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Start the adapter (HTTP server + socket server).

        This does NOT load models - call initialize_engine() for that.
        """
        self._start_time = time.time()
        self._running = True

        # Initialize state
        self.state.pid = os.getpid()
        self.state.started_at = datetime.now(timezone.utc).isoformat()
        self.state.hotkey.key = self._config.hotkey.key
        self.state.output.mode = self._config.output.mode

        # Write PID file
        self._write_pid()

        # Start servers
        self._start_http_server()
        self._start_socket_server()

        logger.info(f"OpenVIPAdapter started (PID: {os.getpid()})")

    def initialize_engine(self, *, headless: bool = True) -> None:
        """Initialize the engine (load models).

        Args:
            headless: If True, suppress console output during loading.
        """
        from voxtype.utils.stats import get_model_load_time

        # Setup loading state
        stt_model_id = self._get_stt_model_id()
        self.state.loading = LoadingState(
            active=True,
            models=[
                LoadingProgress(
                    name="stt",
                    status="pending",
                    estimated=get_model_load_time(stt_model_id) or 20.0,
                ),
                LoadingProgress(
                    name="vad",
                    status="pending",
                    estimated=get_model_load_time("silero-vad") or 5.0,
                ),
            ],
        )

        # Load models
        self._update_loading("stt", "loading")
        self._engine._init_vad_components(headless=headless)

        # Update state after loading
        self._update_loading("stt", "done")
        self._update_loading("vad", "done")
        self.state.loading.active = False
        self.state.stt.model_loaded = True
        self.state.stt.model_name = self._config.stt.model
        self.state.stt.language = self._config.stt.language

        # Start agent discovery
        # Note: VoxtypeEngine handles agent registration internally

    def run(self, *, start_listening: bool = True) -> None:
        """Run the adapter main loop (blocking).

        Args:
            start_listening: If True, start STT in listening mode.
        """
        if start_listening and self._engine:
            self._engine._set_listening(True)
            self.state.stt.state = "listening"

        try:
            while self._running and not self._shutdown_requested:
                # Update uptime
                self.state.uptime_seconds = time.time() - self._start_time

                # Sync state from engine
                self._sync_state_from_engine()

                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the adapter."""
        logger.info("Stopping adapter...")
        self._running = False

        # Stop engine
        if self._engine:
            self._engine.stop()

        # Stop servers
        if self._http_server:
            self._http_server.shutdown()
            self._http_server = None
        if self._http_thread:
            self._http_thread.join(timeout=5)
            self._http_thread = None
        if self._socket_server:
            self._socket_server.stop()
            self._socket_server = None

        # Notify SSE listeners
        self._broadcast_event(None)

        # Remove PID file
        pid_path = get_pid_path()
        if pid_path.exists():
            try:
                pid_path.unlink()
            except Exception:
                pass

        logger.info("Adapter stopped")

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        self._shutdown_requested = True

    # -------------------------------------------------------------------------
    # Status / Control
    # -------------------------------------------------------------------------

    def get_status(self) -> dict:
        """Get current state as dict for /status endpoint."""
        self.state.uptime_seconds = time.time() - self._start_time
        self._sync_state_from_engine()
        return self.state.to_dict()

    def handle_control(self, message: dict) -> dict:
        """Handle OpenVIP control command."""
        return self._control.handle_command(message)

    # -------------------------------------------------------------------------
    # Event Listeners (for SSE)
    # -------------------------------------------------------------------------

    def register_event_listener(self, queue: Queue[dict | None]) -> None:
        with self._event_lock:
            self._event_listeners.append(queue)

    def unregister_event_listener(self, queue: Queue[dict | None]) -> None:
        with self._event_lock:
            if queue in self._event_listeners:
                self._event_listeners.remove(queue)

    def _broadcast_event(self, event: dict | None) -> None:
        with self._event_lock:
            for queue in self._event_listeners:
                try:
                    queue.put_nowait(event)
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _get_stt_model_id(self) -> str:
        from voxtype.utils.hardware import is_mlx_available

        model = self._config.stt.model
        if self._config.stt.hw_accel and is_mlx_available():
            return f"mlx-community/whisper-{model}"
        return f"faster-whisper-{model}"

    def _update_loading(self, model_name: str, status: str) -> None:
        for model in self.state.loading.models:
            if model.name == model_name:
                model.status = status
                if status == "loading":
                    model.elapsed = 0.0
                elif status == "done":
                    # Calculate elapsed from start_time
                    pass
                break

    def _sync_state_from_engine(self) -> None:
        """Sync state from VoxtypeEngine."""
        if not self._engine:
            return

        # Sync STT state
        if self._engine.is_listening:
            self.state.stt.state = "listening"
        elif self._engine.is_off:
            self.state.stt.state = "idle"

        # Sync agents
        self.state.output.available_agents = list(self._engine.agents)
        if self._engine.current_agent:
            self.state.output.current_agent = self._engine.current_agent

    def _start_http_server(self) -> None:
        handler = type("Handler", (AdapterHTTPHandler,), {"adapter": self})
        port = self._config.server.port
        host = self._config.server.host
        self._http_server = ThreadingHTTPServer((host, port), handler)
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever, daemon=True
        )
        self._http_thread.start()
        logger.info(f"HTTP server started on {host}:{port}")

    def _start_socket_server(self) -> None:
        socket_path = get_socket_path()
        self._socket_server = UnixSocketServer(self, socket_path)
        self._socket_server.start()

    def _write_pid(self) -> None:
        pid_path = get_pid_path()
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()))
