"""Server-Sent Events (SSE) server for voxtype - stream events to clients.

Implements OpenVIP (Open Voice Input Protocol) v1.0.
See: https://open-voice-input.org
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any

from voxtype import __version__

if TYPE_CHECKING:
    from voxtype.core.events import TranscriptionResult
    from voxtype.core.state import AppState, ProcessingMode

# OpenVIP protocol version
OPENVIP_VERSION = "1.0"


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
                # Wait for events (handled by _send_event calls from server)
                threading.Event().wait(timeout=30)
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

        event: state
        data: {"openvip": "1.0", "type": "state", "id": "...", "state": "listening", ...}

    All events follow the OpenVIP v1.0 specification.
    See: https://open-voice-input.org
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
    ) -> None:
        """Initialize SSE server.

        Args:
            host: Host to bind to.
            port: Port to listen on.
        """
        self.host = host
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._clients: list[SSEHandler] = []
        self._clients_lock = threading.Lock()

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
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None

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

    def _openvip_message(self, msg_type: str, **kwargs: Any) -> dict[str, Any]:
        """Create an OpenVIP message.

        Args:
            msg_type: Message type (message, partial, start, end, state, error).
            **kwargs: Additional fields for the message.

        Returns:
            OpenVIP message dict.
        """
        message: dict[str, Any] = {
            "openvip": OPENVIP_VERSION,
            "type": msg_type,
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": f"voxtype/{__version__}",
        }
        message.update(kwargs)
        return message

    def send_transcription(
        self,
        text: str,
        language: str | None = None,
        audio_duration_ms: float | None = None,
        transcription_ms: float | None = None,
    ) -> None:
        """Send a transcription event (OpenVIP type: message).

        Args:
            text: Transcribed text.
            language: Language code.
            audio_duration_ms: Audio duration in milliseconds.
            transcription_ms: Transcription time in milliseconds.
        """
        kwargs: dict[str, Any] = {"text": text}
        if language:
            kwargs["language"] = language
        if audio_duration_ms is not None:
            kwargs["audio_duration_ms"] = int(audio_duration_ms)
        if transcription_ms is not None:
            kwargs["transcription_ms"] = int(transcription_ms)

        self._broadcast("message", self._openvip_message("message", **kwargs))

    def send_transcription_result(self, result: TranscriptionResult, language: str | None = None) -> None:
        """Send a TranscriptionResult event.

        Args:
            result: Transcription result from the engine.
            language: Language code.
        """
        self.send_transcription(
            text=result.text,
            language=language,
            audio_duration_ms=result.audio_duration_seconds * 1000,
            transcription_ms=result.transcription_seconds * 1000,
        )

    def send_state_change(self, old: AppState, new: AppState, trigger: str) -> None:
        """Send a state change event (OpenVIP type: state).

        Args:
            old: Previous state.
            new: New state.
            trigger: What triggered the change.
        """
        # Map voxtype states to OpenVIP states
        state_map = {
            "OFF": "idle",
            "LISTENING": "listening",
            "RECORDING": "listening",
            "TRANSCRIBING": "processing",
        }
        openvip_state = state_map.get(new.name, "idle")
        self._broadcast("state", self._openvip_message("state", state=openvip_state))

    def send_mode_change(self, mode: ProcessingMode) -> None:
        """Send a mode change event.

        Note: Processing mode is voxtype-specific, sent as x_ extension.
        """
        self._broadcast("state", self._openvip_message(
            "state",
            state="listening",
            x_mode=mode.value,
        ))

    def send_agent_change(self, agent_name: str, index: int) -> None:
        """Send an agent change event.

        Note: Agent is voxtype-specific, sent as x_ extension.
        """
        self._broadcast("state", self._openvip_message(
            "state",
            state="listening",
            x_agent=agent_name,
            x_agent_index=index,
        ))

    def send_partial_transcription(self, text: str) -> None:
        """Send a partial transcription event (OpenVIP type: partial).

        Args:
            text: Partial transcription text so far.
        """
        self._broadcast("partial", self._openvip_message("partial", text=text))

    def send_error(self, message: str, context: str) -> None:
        """Send an error event (OpenVIP type: error).

        Args:
            message: Error message.
            context: Context where the error occurred.
        """
        self._broadcast("error", self._openvip_message("error", error=message, code=context))

    def send_start(self) -> None:
        """Send a start event (recording started)."""
        self._broadcast("start", self._openvip_message("start"))

    def send_end(self) -> None:
        """Send an end event (recording ended)."""
        self._broadcast("end", self._openvip_message("end"))
