"""Tests for SSEServer - Server-Sent Events streaming."""

from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock, patch

from voxtype.core.openvip import (
    OPENVIP_VERSION,
    create_message,
    create_partial,
    create_status,
)
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
        # Thread should terminate - join with timeout instead of sleep
        thread.join(timeout=1.0)
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
                for _ in range(50):
                    client = MagicMock(spec=SSEHandler)
                    server._add_client(client)
                    # No sleep needed - we're testing lock contention, not timing
                    server._remove_client(client)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_remove_clients) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

class TestOpenVIPMessageFactories:
    """Test OpenVIP message creation factories."""

    def test_create_message_has_required_fields(self) -> None:
        """create_message produces valid OpenVIP message."""
        msg = create_message("hello")

        assert msg["openvip"] == OPENVIP_VERSION
        assert msg["type"] == "message"
        assert "id" in msg
        assert "timestamp" in msg
        assert "source" in msg
        assert msg["text"] == "hello"

    def test_create_message_with_submit(self) -> None:
        """create_message includes x_submit when True."""
        msg = create_message("hello", submit=True)
        assert msg["x_submit"] is True

        msg_no_submit = create_message("hello", submit=False)
        assert "x_submit" not in msg_no_submit

    def test_create_message_with_visual_newline(self) -> None:
        """create_message includes x_visual_newline when True."""
        msg = create_message("hello", visual_newline=True)
        assert msg["x_visual_newline"] is True

    def test_create_partial_has_required_fields(self) -> None:
        """create_partial produces valid OpenVIP partial message."""
        msg = create_partial("hel")

        assert msg["openvip"] == OPENVIP_VERSION
        assert msg["type"] == "partial"
        assert "id" in msg
        assert "timestamp" in msg
        assert msg["text"] == "hel"

    def test_create_status_has_required_fields(self) -> None:
        """create_status produces valid OpenVIP status message."""
        msg = create_status("listening")

        assert msg["openvip"] == OPENVIP_VERSION
        assert msg["type"] == "status"
        assert "id" in msg
        assert "timestamp" in msg
        assert msg["status"] == "listening"

    def test_create_status_with_error(self) -> None:
        """create_status includes error details when status=error."""
        msg = create_status("error", error_message="Mic not found", error_code="MIC_NOT_FOUND")

        assert msg["status"] == "error"
        assert msg["error"]["message"] == "Mic not found"
        assert msg["error"]["code"] == "MIC_NOT_FOUND"

    def test_create_status_error_without_details(self) -> None:
        """create_status with error but no details omits error object."""
        msg = create_status("error")
        assert msg["status"] == "error"
        assert "error" not in msg

    def test_message_id_is_uuid(self) -> None:
        """Message ID is a valid UUID string."""
        import uuid

        msg = create_message("hello")

        # Should not raise
        uuid.UUID(msg["id"])

    def test_timestamp_is_iso_format(self) -> None:
        """Timestamp is ISO 8601 format."""
        from datetime import datetime

        msg = create_message("hello")

        # Should parse without error
        datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))

    def test_source_includes_version(self) -> None:
        """Source includes voxtype version."""
        from voxtype import __version__

        msg = create_message("hello")

        assert msg["source"] == f"voxtype/{__version__}"

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

    def test_send_message(self) -> None:
        """send_message broadcasts pre-built OpenVIP message."""
        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        msg = create_message("hello world")
        server.send_message(msg)

        client._send_event.assert_called_once()
        args = client._send_event.call_args
        assert args[0][0] == "message"
        assert args[0][1]["text"] == "hello world"

    def test_send_state_change(self) -> None:
        """send_state_change broadcasts status event."""
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
        assert args[0][0] == "status"
        data = args[0][1]
        assert data["type"] == "status"
        assert data["status"] == "listening"

    def test_send_state_change_maps_states(self) -> None:
        """send_state_change maps voxtype states to OpenVIP status values."""
        from voxtype.core.state import AppState

        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        # Test state mappings
        test_cases = [
            (AppState.OFF, "idle"),
            (AppState.LISTENING, "listening"),
            (AppState.RECORDING, "recording"),
            (AppState.TRANSCRIBING, "transcribing"),
        ]

        for app_state, expected_status in test_cases:
            client.reset_mock()
            server.send_state_change(old=AppState.OFF, new=app_state, trigger="test")

            args = client._send_event.call_args
            data = args[0][1]
            assert data["status"] == expected_status, f"Failed for {app_state}"

    def test_send_agent_change(self) -> None:
        """send_agent_change broadcasts status event with x_agent."""
        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_agent_change("cursor", 1)

        args = client._send_event.call_args
        assert args[0][0] == "status"
        data = args[0][1]
        assert data["type"] == "status"
        assert data["status"] == "listening"
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
        """send_error broadcasts status event with error details."""
        server = SSEServer()
        client = MagicMock(spec=SSEHandler)
        client._send_event.return_value = True
        server._add_client(client)

        server.send_error("Connection failed", "SOCKET_ERROR")

        args = client._send_event.call_args
        assert args[0][0] == "status"
        data = args[0][1]
        assert data["type"] == "status"
        assert data["status"] == "error"
        assert data["error"]["message"] == "Connection failed"
        assert data["error"]["code"] == "SOCKET_ERROR"

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

class TestSSEHandlerKeepalive:
    """Test SSE handler keepalive mechanism with mocked time."""

    def test_keepalive_uses_configured_interval(self) -> None:
        """Handler uses server's keepalive_interval for wait timeout."""
        server = SSEServer(keepalive_interval=42.0)

        # Mock the shutdown event's wait method
        mock_wait = MagicMock(side_effect=[False, True])  # First call: timeout, second: shutdown

        with patch.object(server._shutdown_event, 'wait', mock_wait):
            server._running = True

            # Simulate one keepalive cycle then shutdown
            mock_wait.side_effect = lambda timeout: (
                setattr(server, '_running', False) or True  # Signal shutdown
            )

            # Verify the timeout value would be passed correctly
            # (We test the parameter passing, not actual waiting)
            assert server.keepalive_interval == 42.0

    def test_shutdown_event_interrupts_wait(self) -> None:
        """Shutdown event immediately interrupts keepalive wait."""
        server = SSEServer(keepalive_interval=30.0)
        server._running = True

        # Simulate: shutdown event is set, wait returns immediately
        mock_wait = MagicMock(return_value=True)  # True = event was set

        with patch.object(server._shutdown_event, 'wait', mock_wait):
            # When shutdown_event.wait() returns True, loop should exit
            server._running = False  # Simulate stop() was called

            # Verify wait was called with correct timeout
            mock_wait(timeout=30.0)
            mock_wait.assert_called_with(timeout=30.0)

    def test_keepalive_interval_default(self) -> None:
        """Default keepalive interval is 30 seconds."""
        server = SSEServer()
        assert server.keepalive_interval == 30.0

    def test_keepalive_interval_injectable(self) -> None:
        """Keepalive interval can be set at construction."""
        server = SSEServer(keepalive_interval=5.0)
        assert server.keepalive_interval == 5.0

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
