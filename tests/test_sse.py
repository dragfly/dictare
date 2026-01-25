"""Tests for SSEServer - Server-Sent Events streaming."""

from __future__ import annotations

import json
import threading
import time
from unittest.mock import MagicMock

from voxtype.core.openvip import OPENVIP_VERSION, create_event
from voxtype.output.sse import SSEHandler, SSEServer

class TestSSEServerInit:
    """Test SSEServer initialization."""

    def test_default_values(self) -> None:
        """Server initializes with default values."""
        server = SSEServer()

        assert server.host == "localhost"
        assert server.port == 8765
        assert server.agent is None
        assert server._running is False
        assert server._server is None
        assert server._thread is None
        assert server._clients == []

    def test_custom_values(self) -> None:
        """Server accepts custom host, port, agent."""
        server = SSEServer(host="0.0.0.0", port=9000, agent="claude")

        assert server.host == "0.0.0.0"
        assert server.port == 9000
        assert server.agent == "claude"

    def test_has_clients_lock(self) -> None:
        """Server has lock for thread-safe client access."""
        server = SSEServer()
        assert hasattr(server, "_clients_lock")
        assert isinstance(server._clients_lock, type(threading.Lock()))

class TestSSEServerLifecycle:
    """Test SSEServer start/stop lifecycle."""

    def test_start_creates_server_and_thread(self) -> None:
        """Start creates HTTP server and background thread."""
        server = SSEServer(port=0)  # Port 0 = random available port
        server.start()

        try:
            assert server._running is True
            assert server._server is not None
            assert server._thread is not None
            assert server._thread.is_alive()
        finally:
            server.stop()

    def test_start_is_idempotent(self) -> None:
        """Starting twice doesn't create multiple servers."""
        server = SSEServer(port=0)
        server.start()

        try:
            first_server = server._server
            first_thread = server._thread

            server.start()

            assert server._server is first_server
            assert server._thread is first_thread
        finally:
            server.stop()

    def test_stop_shuts_down_server(self) -> None:
        """Stop shuts down server and thread."""
        server = SSEServer(port=0)
        server.start()
        thread = server._thread

        server.stop()

        assert server._running is False
        assert server._server is None
        # Thread should terminate
        time.sleep(0.1)
        assert not thread.is_alive()

    def test_stop_is_idempotent(self) -> None:
        """Stopping twice doesn't crash."""
        server = SSEServer(port=0)
        server.start()
        server.stop()
        server.stop()  # Should not crash

class TestSSEServerProperties:
    """Test SSEServer properties."""

    def test_url_property(self) -> None:
        """url property returns correct endpoint URL."""
        server = SSEServer(host="example.com", port=8080)
        assert server.url == "http://example.com:8080/events"

    def test_client_count_initially_zero(self) -> None:
        """client_count is 0 initially."""
        server = SSEServer()
        assert server.client_count == 0

class TestSSEServerClientManagement:
    """Test client connection management."""

    def test_add_client(self) -> None:
        """Can add clients."""
        server = SSEServer()
        mock_client = MagicMock(spec=SSEHandler)

        server._add_client(mock_client)

        assert server.client_count == 1
        assert mock_client in server._clients

    def test_remove_client(self) -> None:
        """Can remove clients."""
        server = SSEServer()
        mock_client = MagicMock(spec=SSEHandler)

        server._add_client(mock_client)
        server._remove_client(mock_client)

        assert server.client_count == 0
        assert mock_client not in server._clients

    def test_remove_nonexistent_client(self) -> None:
        """Removing nonexistent client doesn't crash."""
        server = SSEServer()
        mock_client = MagicMock(spec=SSEHandler)

        server._remove_client(mock_client)  # Should not crash

    def test_client_operations_are_thread_safe(self) -> None:
        """Client add/remove is thread-safe."""
        server = SSEServer()
        errors = []

        def add_remove_clients() -> None:
            try:
                for i in range(50):
                    client = MagicMock(spec=SSEHandler)
                    server._add_client(client)
                    time.sleep(0.001)
                    server._remove_client(client)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_remove_clients) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

class TestOpenVIPMessage:
    """Test OpenVIP message creation via create_event factory."""

    def test_message_has_required_fields(self) -> None:
        """OpenVIP messages have required fields."""
        msg = create_event("message", text="hello")

        assert msg["openvip"] == OPENVIP_VERSION
        assert msg["type"] == "message"
        assert "id" in msg
        assert "timestamp" in msg
        assert "source" in msg
        assert msg["text"] == "hello"

    def test_message_id_is_uuid(self) -> None:
        """Message ID is a valid UUID string."""
        import uuid

        msg = create_event("message")

        # Should not raise
        uuid.UUID(msg["id"])

    def test_timestamp_is_iso_format(self) -> None:
        """Timestamp is ISO 8601 format."""
        from datetime import datetime

        msg = create_event("message")

        # Should parse without error
        datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))

    def test_source_includes_version(self) -> None:
        """Source includes voxtype version."""
        from voxtype import __version__

        msg = create_event("message")

        assert msg["source"] == f"voxtype/{__version__}"

    def test_extra_kwargs_added(self) -> None:
        """Extra kwargs are added to message."""
        msg = create_event(
            "message",
            text="hello",
            language="en",
            custom_field="custom_value",
        )

        assert msg["text"] == "hello"
        assert msg["language"] == "en"
        assert msg["custom_field"] == "custom_value"

class TestSSEServerBroadcast:
    """Test event broadcasting."""

    def test_broadcast_sends_to_all_clients(self) -> None:
        """Broadcast sends event to all connected clients."""
        server = SSEServer()

        clients = [MagicMock(spec=SSEHandler) for _ in range(3)]
        for client in clients:
            client._send_event.return_value = True
            server._add_client(client)

        server._broadcast("message", {"text": "hello"})

        for client in clients:
            client._send_event.assert_called_once_with("message", {"text": "hello"})

    def test_broadcast_removes_dead_clients(self) -> None:
        """Broadcast removes clients that fail to receive."""
        server = SSEServer()

        good_client = MagicMock(spec=SSEHandler)
        good_client._send_event.return_value = True

        dead_client = MagicMock(spec=SSEHandler)
        dead_client._send_event.return_value = False  # Connection failed

        server._add_client(good_client)
        server._add_client(dead_client)

        server._broadcast("message", {"text": "hello"})

        assert server.client_count == 1
        assert good_client in server._clients
        assert dead_client not in server._clients

class TestSSEServerEvents:
    """Test event sending methods."""

    def test_send_transcription(self) -> None:
        """send_transcription broadcasts message event."""
        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_transcription(
            text="hello world",
            language="en",
            audio_duration_ms=1500.5,
            transcription_ms=250.3,
        )

        client._send_event.assert_called_once()
        args = client._send_event.call_args
        assert args[0][0] == "message"  # Event type

        data = args[0][1]
        assert data["type"] == "message"
        assert data["text"] == "hello world"
        assert data["language"] == "en"
        assert data["audio_duration_ms"] == 1500
        assert data["transcription_ms"] == 250

    def test_send_transcription_optional_fields(self) -> None:
        """send_transcription works with only text."""
        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_transcription(text="hello")

        args = client._send_event.call_args
        data = args[0][1]
        assert "language" not in data
        assert "audio_duration_ms" not in data
        assert "transcription_ms" not in data

    def test_send_transcription_result(self) -> None:
        """send_transcription_result handles TranscriptionResult."""
        from voxtype.core.events import TranscriptionResult

        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        result = TranscriptionResult(
            text="hello",
            audio_duration_seconds=1.5,
            transcription_seconds=0.25,
        )
        server.send_transcription_result(result, language="en")

        args = client._send_event.call_args
        data = args[0][1]
        assert data["text"] == "hello"
        assert data["language"] == "en"
        assert data["audio_duration_ms"] == 1500
        assert data["transcription_ms"] == 250

    def test_send_state_change(self) -> None:
        """send_state_change broadcasts state event."""
        from voxtype.core.state import AppState

        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_state_change(
            old=AppState.OFF,
            new=AppState.LISTENING,
            trigger="hotkey",
        )

        args = client._send_event.call_args
        assert args[0][0] == "state"
        data = args[0][1]
        assert data["type"] == "state"
        assert data["state"] == "listening"

    def test_send_state_change_maps_states(self) -> None:
        """send_state_change maps voxtype states to OpenVIP states."""
        from voxtype.core.state import AppState

        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        # Test state mappings
        test_cases = [
            (AppState.OFF, "idle"),
            (AppState.LISTENING, "listening"),
            (AppState.RECORDING, "listening"),
            (AppState.TRANSCRIBING, "processing"),
        ]

        for app_state, expected_openvip in test_cases:
            client.reset_mock()
            server.send_state_change(old=AppState.OFF, new=app_state, trigger="test")

            args = client._send_event.call_args
            data = args[0][1]
            assert data["state"] == expected_openvip, f"Failed for {app_state}"

    def test_send_mode_change(self) -> None:
        """send_mode_change broadcasts state event with x_mode."""
        from voxtype.core.state import ProcessingMode

        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_mode_change(ProcessingMode.COMMAND)

        args = client._send_event.call_args
        assert args[0][0] == "state"
        data = args[0][1]
        assert data["x_mode"] == "command"

    def test_send_agent_change(self) -> None:
        """send_agent_change broadcasts state event with x_agent."""
        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_agent_change("cursor", 1)

        args = client._send_event.call_args
        assert args[0][0] == "state"
        data = args[0][1]
        assert data["x_agent"] == "cursor"
        assert data["x_agent_index"] == 1

    def test_send_partial_transcription(self) -> None:
        """send_partial_transcription broadcasts partial event."""
        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_partial_transcription("hello wor")

        args = client._send_event.call_args
        assert args[0][0] == "partial"
        data = args[0][1]
        assert data["type"] == "partial"
        assert data["text"] == "hello wor"

    def test_send_error(self) -> None:
        """send_error broadcasts error event."""
        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_error("Connection failed", "socket")

        args = client._send_event.call_args
        assert args[0][0] == "error"
        data = args[0][1]
        assert data["type"] == "error"
        assert data["error"] == "Connection failed"
        assert data["code"] == "socket"

    def test_send_start(self) -> None:
        """send_start broadcasts start event."""
        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_start()

        args = client._send_event.call_args
        assert args[0][0] == "start"
        data = args[0][1]
        assert data["type"] == "start"

    def test_send_end(self) -> None:
        """send_end broadcasts end event."""
        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_end()

        args = client._send_event.call_args
        assert args[0][0] == "end"
        data = args[0][1]
        assert data["type"] == "end"

class TestSSEHandler:
    """Test SSEHandler request handling."""

    def test_log_message_suppressed(self) -> None:
        """log_message is suppressed (no output)."""
        handler = MagicMock(spec=SSEHandler)
        SSEHandler.log_message(handler, "test %s", "arg")
        # Should not crash - logging is suppressed

    def test_send_event_format(self) -> None:
        """_send_event formats SSE correctly."""
        # Create mock wfile
        mock_wfile = MagicMock()

        # Create handler with mocked attributes
        handler = SSEHandler.__new__(SSEHandler)
        handler.wfile = mock_wfile

        result = handler._send_event("message", {"text": "hello"})

        assert result is True
        mock_wfile.write.assert_called_once()
        written = mock_wfile.write.call_args[0][0].decode("utf-8")

        assert written.startswith("event: message\n")
        assert "data: " in written
        assert written.endswith("\n\n")

        # Parse the data
        data_line = [line for line in written.split("\n") if line.startswith("data: ")][0]
        data = json.loads(data_line[6:])  # Strip "data: "
        assert data["text"] == "hello"

    def test_send_event_handles_connection_error(self) -> None:
        """_send_event returns False on connection error."""
        mock_wfile = MagicMock()
        mock_wfile.write.side_effect = BrokenPipeError()

        handler = SSEHandler.__new__(SSEHandler)
        handler.wfile = mock_wfile

        result = handler._send_event("message", {"text": "hello"})

        assert result is False

    def test_send_event_handles_connection_reset(self) -> None:
        """_send_event returns False on connection reset."""
        mock_wfile = MagicMock()
        mock_wfile.write.side_effect = ConnectionResetError()

        handler = SSEHandler.__new__(SSEHandler)
        handler.wfile = mock_wfile

        result = handler._send_event("message", {"text": "hello"})

        assert result is False

    def test_send_event_handles_os_error(self) -> None:
        """_send_event returns False on OSError."""
        mock_wfile = MagicMock()
        mock_wfile.write.side_effect = OSError()

        handler = SSEHandler.__new__(SSEHandler)
        handler.wfile = mock_wfile

        result = handler._send_event("message", {"text": "hello"})

        assert result is False

class TestSSEIntegration:
    """Integration tests with real HTTP connections."""

    def test_server_accepts_connections(self) -> None:
        """Server accepts HTTP connections."""
        import socket
        import threading

        server = SSEServer(port=0)
        server.start()

        result = {}

        def connect_and_read() -> None:
            try:
                actual_port = server._server.server_address[1]
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect(("localhost", actual_port))

                # Send HTTP request
                request = b"GET /events HTTP/1.1\r\nHost: localhost\r\n\r\n"
                sock.sendall(request)

                # Read response headers
                response = b""
                while b"\r\n\r\n" not in response:
                    chunk = sock.recv(1024)
                    if not chunk:
                        break
                    response += chunk

                result["response"] = response.decode("utf-8")
                sock.close()
            except Exception as e:
                result["error"] = str(e)

        try:
            # Run in thread to avoid blocking
            t = threading.Thread(target=connect_and_read)
            t.start()
            t.join(timeout=3)

            assert "error" not in result, f"Connection error: {result.get('error')}"
            assert "200 OK" in result.get("response", "")
            assert "text/event-stream" in result.get("response", "")
            assert "Access-Control-Allow-Origin: *" in result.get("response", "")
        finally:
            server.stop()

    def test_server_returns_404_for_wrong_path(self) -> None:
        """Server returns 404 for non-/events paths."""
        import socket
        import threading

        server = SSEServer(port=0)
        server.start()

        result = {}

        def connect_and_read() -> None:
            try:
                actual_port = server._server.server_address[1]
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect(("localhost", actual_port))

                # Send HTTP request to wrong path
                request = b"GET /wrong-path HTTP/1.1\r\nHost: localhost\r\n\r\n"
                sock.sendall(request)

                # Read response
                response = sock.recv(4096)
                result["response"] = response.decode("utf-8")
                sock.close()
            except Exception as e:
                result["error"] = str(e)

        try:
            t = threading.Thread(target=connect_and_read)
            t.start()
            t.join(timeout=3)

            assert "error" not in result, f"Connection error: {result.get('error')}"
            assert "404" in result.get("response", "")
        finally:
            server.stop()
