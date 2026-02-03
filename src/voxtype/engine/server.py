"""Transport layer: HTTP server and Unix socket server.

Provides identical API over both transports:
- Unix socket: ~/.voxtype/engine.sock (low latency, local only)
- HTTP: port 9876 (configurable, for remote access and SSE)
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from voxtype.engine.engine import Engine

logger = logging.getLogger(__name__)

class EngineHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for engine endpoints."""

    # Reference to engine (set by factory)
    engine: Engine

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Send JSON response."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code: str, message: str, status: int = 400) -> None:
        """Send error response."""
        self._send_json({"error": {"code": code, "message": message}}, status)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/status":
            self._handle_status()
        elif self.path == "/config":
            self._handle_config()
        elif self.path == "/metrics":
            self._handle_metrics()
        elif self.path == "/events":
            self._handle_events()
        else:
            self._send_error("NOT_FOUND", f"Unknown endpoint: {self.path}", 404)

    def do_POST(self) -> None:
        """Handle POST requests."""
        if self.path == "/control":
            self._handle_control()
        else:
            self._send_error("NOT_FOUND", f"Unknown endpoint: {self.path}", 404)

    def _handle_status(self) -> None:
        """GET /status - return engine state."""
        state = self.engine.get_status()
        self._send_json(state)

    def _handle_config(self) -> None:
        """GET /config - return engine configuration."""
        config = self.engine.get_config()
        self._send_json(config)

    def _handle_metrics(self) -> None:
        """GET /metrics - return engine metrics."""
        metrics = self.engine.get_metrics()
        self._send_json(metrics)

    def _handle_control(self) -> None:
        """POST /control - receive OpenVIP control command."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            message = json.loads(body)
        except json.JSONDecodeError as e:
            self._send_error("INVALID_JSON", str(e))
            return

        # Validate OpenVIP message
        if message.get("openvip") != "1.0":
            self._send_error("INVALID_PROTOCOL", "openvip must be '1.0'")
            return
        if message.get("type") != "control":
            self._send_error("INVALID_TYPE", "type must be 'control'")
            return

        # Handle command
        response = self.engine.handle_control(message)
        status_code = 200 if response.get("status") == "ok" else 400
        self._send_json(response, status_code)

    def _handle_events(self) -> None:
        """GET /events - SSE stream of OpenVIP events."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Register for events
        event_queue: Queue[dict[Any, Any] | None] = Queue()
        self.engine.register_event_listener(event_queue)

        try:
            while True:
                event = event_queue.get()
                if event is None:  # Shutdown signal
                    break
                data = json.dumps(event)
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.engine.unregister_event_listener(event_queue)

class HTTPServer:
    """HTTP server for engine API."""

    def __init__(self, engine: Engine, port: int = 9876, host: str = "127.0.0.1") -> None:
        """Initialize HTTP server.

        Args:
            engine: The engine instance.
            port: Port to listen on.
            host: Host to bind to.
        """
        self._engine = engine
        self._port = port
        self._host = host
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the HTTP server."""
        # Create handler class with engine reference
        handler = type(
            "Handler",
            (EngineHTTPHandler,),
            {"engine": self._engine},
        )

        self._server = ThreadingHTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"HTTP server started on {self._host}:{self._port}")

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def url(self) -> str:
        """Get server URL."""
        return f"http://{self._host}:{self._port}"

class UnixSocketServer:
    """Unix socket server for engine API.

    Protocol: JSON newline-delimited
    Request: {"endpoint": "/status"} or {"endpoint": "/control", "body": {...}}
    Response: {"status": 200, "body": {...}}
    """

    def __init__(self, engine: Engine, socket_path: Path | str) -> None:
        """Initialize Unix socket server.

        Args:
            engine: The engine instance.
            socket_path: Path to the Unix socket.
        """
        self._engine = engine
        self._socket_path = Path(socket_path)
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Start the Unix socket server."""
        # Remove existing socket
        if self._socket_path.exists():
            self._socket_path.unlink()

        # Create parent directory
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Create socket
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self._socket_path))
        self._server.listen(5)
        self._server.settimeout(1.0)  # Allow periodic check for shutdown

        self._running = True
        self._thread = threading.Thread(target=self._serve_loop, daemon=True)
        self._thread.start()
        logger.info(f"Unix socket server started on {self._socket_path}")

    def stop(self) -> None:
        """Stop the Unix socket server."""
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

        # Remove socket file
        if self._socket_path.exists():
            try:
                self._socket_path.unlink()
            except Exception:
                pass

    def _serve_loop(self) -> None:
        """Main server loop."""
        while self._running and self._server:
            try:
                conn, _ = self._server.accept()
                # Handle each connection in a new thread
                threading.Thread(
                    target=self._handle_connection,
                    args=(conn,),
                    daemon=True,
                ).start()
            except TimeoutError:
                continue
            except OSError:
                break

    def _handle_connection(self, conn: socket.socket) -> None:
        """Handle a single connection."""
        try:
            conn.settimeout(30)  # 30 second timeout

            # Read request (newline-delimited JSON)
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

            # Parse request
            try:
                request = json.loads(data.decode("utf-8").strip())
            except json.JSONDecodeError as e:
                response = {"status": 400, "error": str(e)}
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                return

            # Route request
            endpoint = request.get("endpoint", "")
            body = request.get("body", {})

            if endpoint == "/status":
                result = self._engine.get_status()
                response = {"status": 200, "body": result}
            elif endpoint == "/config":
                result = self._engine.get_config()
                response = {"status": 200, "body": result}
            elif endpoint == "/metrics":
                result = self._engine.get_metrics()
                response = {"status": 200, "body": result}
            elif endpoint == "/control":
                # Validate OpenVIP message
                if body.get("openvip") != "1.0":
                    response = {"status": 400, "error": "openvip must be '1.0'"}
                elif body.get("type") != "control":
                    response = {"status": 400, "error": "type must be 'control'"}
                else:
                    result = self._engine.handle_control(body)
                    status = 200 if result.get("status") == "ok" else 400
                    response = {"status": status, "body": result}
            else:
                response = {"status": 404, "error": f"Unknown endpoint: {endpoint}"}

            # Send response
            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

        except TimeoutError:
            pass
        except Exception as e:
            logger.exception(f"Error handling connection: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
