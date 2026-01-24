"""Server-Sent Events (SSE) server for voxtype - stream events to clients."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING, Any

from voxtype import __version__

if TYPE_CHECKING:
    from voxtype.core.events import TranscriptionResult, InjectionResult
    from voxtype.core.state import AppState, ProcessingMode

class SSEHandler(BaseHTTPRequestHandler):
    """HTTP handler for SSE connections."""

    # Reference to SSEServer instance (set by server)
    sse_server: "SSEServer | None" = None

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

    Clients connect to http://localhost:port/events and receive events as:

        event: transcription
        data: {"openvox": "1.0", "type": "message", "text": "hello world", ...}

        event: state_change
        data: {"old": "LISTENING", "new": "RECORDING", "trigger": "vad_speech_start"}

    Events are OpenVox-compatible where applicable.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        agent: str | None = None,
    ) -> None:
        """Initialize SSE server.

        Args:
            host: Host to bind to.
            port: Port to listen on.
            agent: Optional agent name for context.
        """
        self.host = host
        self.port = port
        self.agent = agent
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

    def send_transcription(
        self,
        text: str,
        language: str | None = None,
        audio_duration_ms: float | None = None,
        transcription_ms: float | None = None,
    ) -> None:
        """Send a transcription event.

        Args:
            text: Transcribed text.
            language: Language code.
            audio_duration_ms: Audio duration in milliseconds.
            transcription_ms: Transcription time in milliseconds.
        """
        data: dict[str, Any] = {
            "openvox": "1.0",
            "type": "message",
            "text": text,
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "context": {
                "source": "voxtype",
                "source_version": __version__,
            },
        }
        if language:
            data["metadata"]["language"] = language
        if audio_duration_ms is not None:
            data["metadata"]["audio_duration_ms"] = audio_duration_ms
        if transcription_ms is not None:
            data["metadata"]["transcription_ms"] = transcription_ms
        if self.agent:
            data["context"]["agent"] = self.agent

        self._broadcast("transcription", data)

    def send_transcription_result(self, result: "TranscriptionResult", language: str | None = None) -> None:
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

    def send_state_change(self, old: "AppState", new: "AppState", trigger: str) -> None:
        """Send a state change event.

        Args:
            old: Previous state.
            new: New state.
            trigger: What triggered the change.
        """
        self._broadcast("state_change", {
            "old": old.name,
            "new": new.name,
            "trigger": trigger,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def send_mode_change(self, mode: "ProcessingMode") -> None:
        """Send a mode change event.

        Args:
            mode: New processing mode.
        """
        self._broadcast("mode_change", {
            "mode": mode.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def send_agent_change(self, agent_name: str, index: int) -> None:
        """Send an agent change event.

        Args:
            agent_name: Name of the new active agent.
            index: Index of the new active agent.
        """
        self._broadcast("agent_change", {
            "agent": agent_name,
            "index": index,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def send_partial_transcription(self, text: str) -> None:
        """Send a partial transcription event (realtime).

        Args:
            text: Partial transcription text so far.
        """
        self._broadcast("partial_transcription", {
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def send_error(self, message: str, context: str) -> None:
        """Send an error event.

        Args:
            message: Error message.
            context: Context where the error occurred.
        """
        self._broadcast("error", {
            "message": message,
            "context": context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
