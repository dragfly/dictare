"""Server-Sent Events (SSE) server for voxtype - stream events to clients.

Implements OpenVIP (Open Voice Input Protocol) v1.0.
See: https://open-voice-input.org

v1.0 Message Types:
- message: Final text to inject
- partial: Streaming partial transcription
- status: Engine state (idle, listening, recording, transcribing, error)
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any

from voxtype import __version__
from voxtype.adapters.openvip.messages import StatusValue, create_partial, create_status

if TYPE_CHECKING:
    from voxtype.core.state import AppState


class SSEHandler(BaseHTTPRequestHandler):
    """HTTP handler for SSE connections."""

    # Reference to SSEServer instance (set by server)
    sse_server: SSEServer | None = None

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress HTTP request logging."""
        pass

    def do_GET(self) -> None:
        """Handle GET request - establish SSE connection."""
        if self.path != "/events":
            self.send_error(404, "Not Found")
            return

        # Set up SSE response headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Register this connection
        if self.sse_server:
            self.sse_server._add_client(self)

        # Send initial connection event
        self._send_event("connected", {
            "source": "voxtype",
            "version": __version__,
        })

        # Keep connection open
        try:
            while self.sse_server and self.sse_server._running:
                # Wait for shutdown or keepalive timeout
                self.sse_server._shutdown_event.wait(
                    timeout=self.sse_server.keepalive_interval
                )
                if not self.sse_server._running:
                    break
                # Send keepalive comment
                try:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
        finally:
            if self.sse_server:
                self.sse_server._remove_client(self)

    def _send_event(self, event_type: str, data: dict) -> bool:
        """Send an SSE event to this client.

        Args:
            event_type: Event type name.
            data: Event data as dict.

        Returns:
            True if sent successfully, False if connection failed.
        """
        try:
            # SSE format: event: <type>\ndata: <json>\n\n
            event_str = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            self.wfile.write(event_str.encode("utf-8"))
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False


class SSEServer:
    """Server-Sent Events server for streaming voxtype events.

    Clients connect to http://localhost:port/events and receive OpenVIP messages:

        event: message
        data: {"openvip": "1.0", "type": "message", "id": "...", "text": "hello", ...}

        event: status
        data: {"openvip": "1.0", "type": "status", "id": "...", "status": "listening", ...}

    All events follow the OpenVIP v1.0 specification.
    See: https://open-voice-input.org
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        agent: str | None = None,
        keepalive_interval: float = 30.0,
    ) -> None:
        """Initialize SSE server.

        Args:
            host: Host to bind to.
            port: Port to listen on.
            agent: Optional agent name for context.
            keepalive_interval: Seconds between keepalive messages.
        """
        self.host = host
        self.port = port
        self.agent = agent
        self.keepalive_interval = keepalive_interval
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._clients: list[SSEHandler] = []
        self._clients_lock = threading.Lock()
        self._shutdown_event = threading.Event()

    def start(self) -> None:
        """Start the SSE server in a background thread."""
        if self._running:
            return

        # Set up handler class with reference to this server
        handler_class = type(
            "SSEHandlerWithServer",
            (SSEHandler,),
            {"sse_server": self}
        )

        self._server = HTTPServer((self.host, self.port), handler_class)
        self._running = True

        self._thread = threading.Thread(
            target=self._serve,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the SSE server."""
        self._running = False
        self._shutdown_event.set()  # Wake up waiting handlers
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None
        self._shutdown_event.clear()  # Reset for potential restart

    def _serve(self) -> None:
        """Serve requests (runs in background thread)."""
        if self._server:
            self._server.serve_forever()

    def _add_client(self, client: SSEHandler) -> None:
        """Add a client connection."""
        with self._clients_lock:
            self._clients.append(client)

    def _remove_client(self, client: SSEHandler) -> None:
        """Remove a client connection."""
        with self._clients_lock:
            if client in self._clients:
                self._clients.remove(client)

    def _broadcast(self, event_type: str, data: dict) -> None:
        """Broadcast an event to all connected clients."""
        with self._clients_lock:
            dead_clients = []
            for client in self._clients:
                if not client._send_event(event_type, data):
                    dead_clients.append(client)
            # Remove dead clients
            for client in dead_clients:
                self._clients.remove(client)

    @property
    def client_count(self) -> int:
        """Number of connected clients."""
        with self._clients_lock:
            return len(self._clients)

    @property
    def url(self) -> str:
        """SSE endpoint URL."""
        return f"http://{self.host}:{self.port}/events"

    # Event methods - called by engine/app

    def send_message(self, message: dict[str, Any]) -> None:
        """Broadcast a pre-built OpenVIP message.

        This is the preferred method - engine creates message with ID,
        transport forwards it transparently.

        Args:
            message: Complete OpenVIP message dict.
        """
        event_type = message.get("type", "message")
        self._broadcast(event_type, message)

    def send_state_change(self, old: AppState, new: AppState, trigger: str) -> None:
        """Send a status message on state change (OpenVIP type: status).

        Args:
            old: Previous state.
            new: New state.
            trigger: What triggered the change (unused, for logging).
        """
        # Map voxtype states to OpenVIP status values
        state_map: dict[str, StatusValue] = {
            "OFF": "idle",
            "LISTENING": "listening",
            "RECORDING": "recording",
            "TRANSCRIBING": "transcribing",
            "INJECTING": "transcribing",  # Still processing
            "PLAYING": "listening",  # TTS feedback
        }
        status: StatusValue = state_map.get(new.name, "idle")
        self._broadcast("status", create_status(status))

    def send_agent_change(self, agent_name: str, index: int) -> None:
        """Send a status message with agent info (voxtype extension).

        Args:
            agent_name: Name of the active agent.
            index: Agent index in the list.
        """
        msg = create_status("listening")
        msg["x_agent"] = agent_name
        msg["x_agent_index"] = index
        self._broadcast("status", msg)

    def send_partial_transcription(self, text: str) -> None:
        """Send a partial transcription (OpenVIP type: partial).

        Args:
            text: Partial transcription text so far.
        """
        self._broadcast("partial", create_partial(text))

    def send_error(self, message: str, code: str | None = None) -> None:
        """Send an error status (OpenVIP type: status with status=error).

        Args:
            message: Error message.
            code: Optional error code.
        """
        self._broadcast("status", create_status("error", error_message=message, error_code=code))
