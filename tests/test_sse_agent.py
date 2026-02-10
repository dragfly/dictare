"""Tests for SSEAgent message delivery and mux status logic."""

from __future__ import annotations

import http.server
import json
import queue
import threading

from voxtype.agent.base import BaseAgent, OpenVIPMessage
from voxtype.agent.mux import _poll_active_agent, _read_from_sse
from voxtype.agent.sse import SSEAgent


class MockServer:
    """Mock OpenVIPServer for testing SSEAgent."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []
        self._return_value = True

    def put_message(self, agent_id: str, message: dict) -> bool:
        self.messages.append((agent_id, message))
        return self._return_value


class TestSSEAgentInit:
    """Test SSEAgent initialization."""

    def test_id_property(self) -> None:
        """Agent exposes its ID."""
        server = MockServer()
        agent = SSEAgent("claude", server)
        assert agent.id == "claude"

    def test_is_base_agent(self) -> None:
        """SSEAgent is a BaseAgent subclass."""
        server = MockServer()
        agent = SSEAgent("test", server)
        assert isinstance(agent, BaseAgent)

    def test_repr(self) -> None:
        """Agent has a useful repr."""
        server = MockServer()
        agent = SSEAgent("my-agent", server)
        assert "SSEAgent" in repr(agent)
        assert "my-agent" in repr(agent)


class TestSSEAgentSend:
    """Test SSEAgent.send() method."""

    def test_send_delegates_to_server(self) -> None:
        """send() calls server.put_message() with correct args."""
        server = MockServer()
        agent = SSEAgent("claude", server)

        message: OpenVIPMessage = {
            "openvip": "1.0",
            "type": "message",
            "text": "hello world",
        }
        result = agent.send(message)

        assert result is True
        assert len(server.messages) == 1
        assert server.messages[0] == ("claude", message)

    def test_send_returns_false_when_not_connected(self) -> None:
        """send() returns False when server can't deliver."""
        server = MockServer()
        server._return_value = False
        agent = SSEAgent("ghost", server)

        result = agent.send({"text": "hello"})
        assert result is False

    def test_send_multiple_messages(self) -> None:
        """Multiple messages are delivered in order."""
        server = MockServer()
        agent = SSEAgent("test", server)

        for i in range(5):
            agent.send({"text": f"msg-{i}"})

        assert len(server.messages) == 5
        for i in range(5):
            assert server.messages[i][1]["text"] == f"msg-{i}"

    def test_send_preserves_message_content(self) -> None:
        """Message content is passed through unchanged."""
        server = MockServer()
        agent = SSEAgent("test", server)

        msg: OpenVIPMessage = {
            "openvip": "1.0",
            "type": "message",
            "id": "abc-123",
            "timestamp": "2026-01-01T00:00:00Z",
            "text": "hello",
            "x_submit": {"enter": True},
            "language": "en",
        }
        agent.send(msg)

        delivered = server.messages[0][1]
        assert delivered is msg  # Same dict reference


class TestSSEAgentThreadSafety:
    """Test SSEAgent thread safety."""

    def test_concurrent_sends(self) -> None:
        """Multiple threads can send concurrently without errors."""
        server = MockServer()
        agent = SSEAgent("test", server)
        errors: list[Exception] = []

        def send_many(thread_id: int) -> None:
            try:
                for i in range(50):
                    agent.send({"text": f"t{thread_id}-{i}"})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=send_many, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(server.messages) == 250  # 5 threads * 50 messages


def _make_status_handler(agent_id: str, current_agent: str):
    """Create an HTTP handler that serves /status JSON."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                body = json.dumps({
                    "platform": {"output": {"current_agent": current_agent}},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/agents/"):
                # SSE endpoint — send one event then close
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                msg = json.dumps({"type": "heartbeat"})
                self.wfile.write(f"data: {msg}\n\n".encode())
                self.wfile.flush()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress logs

    return Handler


class TestPollActiveAgentStatus:
    """Test _poll_active_agent status updates."""

    def test_poll_updates_status_on_active(self) -> None:
        """Polling sets 'listening' when agent is active."""
        handler = _make_status_handler("myagent", "myagent")
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        stop = threading.Event()
        statuses: list[tuple[str, str]] = []

        def on_status(text, style):
            statuses.append((text, style))
            stop.set()  # Stop after first update

        _poll_active_agent("myagent", f"http://127.0.0.1:{port}", stop, on_status,
                           poll_interval=0.05)
        server.server_close()

        assert len(statuses) >= 1
        assert "listening" in statuses[0][0]
        assert statuses[0][1] == "ok"

    def test_poll_resets_was_active_on_error(self) -> None:
        """After connection error, next success forces status update."""
        # Use a port with no server to simulate connection error
        statuses: list[tuple[str, str]] = []

        handler = _make_status_handler("myagent", "myagent")
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        server.server_close()  # Close immediately — first poll will fail

        def on_status(text, style):
            statuses.append((text, style))

        # Run poll once — will fail (server closed), was_active resets to None
        # Then start server and poll again — should force "listening" update
        # We test this indirectly: poll twice, second time with server up

        # First: poll against closed port (error → was_active = None)
        stop_once = threading.Event()

        def poll_once():
            _poll_active_agent("myagent", f"http://127.0.0.1:{port}", stop_once,
                               on_status, poll_interval=0.01)

        pt = threading.Thread(target=poll_once, daemon=True)
        pt.start()
        # Let it poll once (error)
        import time
        time.sleep(0.05)
        stop_once.set()
        pt.join(timeout=1)

        # No status update on error
        assert len(statuses) == 0

        # Now start server and poll again
        server2 = http.server.HTTPServer(("127.0.0.1", port), handler)
        t = threading.Thread(target=server2.handle_request, daemon=True)
        t.start()

        stop2 = threading.Event()

        def on_status2(text, style):
            statuses.append((text, style))
            stop2.set()

        _poll_active_agent("myagent", f"http://127.0.0.1:{port}", stop2, on_status2,
                           poll_interval=0.05)
        server2.server_close()

        # Should have gotten "listening" since was_active was reset
        assert len(statuses) >= 1
        assert "listening" in statuses[0][0]


class TestSSEReconnectStatus:
    """Test _read_from_sse emits 'connected' status on reconnect."""

    def test_sse_connect_emits_status_ok(self) -> None:
        """SSE connection success calls on_status with 'connected'."""
        handler = _make_status_handler("myagent", "myagent")
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        stop = threading.Event()
        statuses: list[tuple[str, str]] = []
        wq: queue.Queue = queue.Queue()

        def on_status(text, style):
            statuses.append((text, style))
            stop.set()  # Stop after first status

        _read_from_sse(
            "myagent",
            f"http://127.0.0.1:{port}",
            wq, stop,
            on_status=on_status,
        )
        server.server_close()

        assert len(statuses) >= 1
        assert "connected" in statuses[0][0]
        assert statuses[0][1] == "ok"

    def test_sse_error_then_reconnect_updates_status(self) -> None:
        """After SSE error, successful reconnect shows 'connected'."""
        handler = _make_status_handler("myagent", "myagent")
        # First: no server → error status
        # Then: server up → connected status
        stop = threading.Event()
        statuses: list[tuple[str, str]] = []
        wq: queue.Queue = queue.Queue()

        # Use a free port
        temp_server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        port = temp_server.server_address[1]
        temp_server.server_close()

        connect_count = [0]

        def on_status(text, style):
            statuses.append((text, style))
            # After getting "connected" (second status), stop
            if "connected" in text and style == "ok":
                connect_count[0] += 1
                if connect_count[0] >= 1:
                    stop.set()

        # Start server after a short delay so first attempt fails
        def start_server_later():
            import time
            time.sleep(0.3)
            server = http.server.HTTPServer(("127.0.0.1", port), handler)
            server.handle_request()
            server.server_close()

        delayed = threading.Thread(target=start_server_later, daemon=True)
        delayed.start()

        _read_from_sse(
            "myagent",
            f"http://127.0.0.1:{port}",
            wq, stop,
            on_status=on_status,
        )

        # Should have error first, then connected
        error_statuses = [(t, s) for t, s in statuses if s == "error"]
        ok_statuses = [(t, s) for t, s in statuses if s == "ok"]
        assert len(error_statuses) >= 1, f"Expected error status, got: {statuses}"
        assert len(ok_statuses) >= 1, f"Expected ok status, got: {statuses}"


class TestWriteToPtyAtomic:
    """Test that _write_to_pty writes text + newline + submit as single os.write()."""

    def _run_writer(self, data: dict) -> tuple[list[bytes], int]:
        """Helper: run _write_to_pty with one message, return (writes, drain_count)."""
        from unittest.mock import patch

        from voxtype.agent.mux import _write_to_pty

        wq: queue.Queue = queue.Queue()
        stop = threading.Event()
        writes: list[bytes] = []
        drain_count = [0]

        def fake_write(fd, data_bytes):
            writes.append(data_bytes)
            stop.set()  # Stop after first write
            return len(data_bytes)

        def fake_tcdrain(fd):
            drain_count[0] += 1

        wq.put(("msg", data))

        with patch("os.write", side_effect=fake_write), \
             patch("termios.tcdrain", side_effect=fake_tcdrain):
            _write_to_pty(master_fd=99, write_queue=wq, stop_event=stop)

        return writes, drain_count[0]

    def test_text_with_submit_single_write(self) -> None:
        """Text + submit must be written in one os.write() call."""
        writes, _ = self._run_writer({"text": "hello world", "submit": True})
        assert len(writes) == 1
        assert writes[0] == b"hello world\r"

    def test_text_with_visual_newline_and_submit_single_write(self) -> None:
        """Text ending with \\n + submit = single write with text + alt_enter + enter."""
        writes, _ = self._run_writer({"text": "line one\n", "submit": True})
        assert len(writes) == 1
        # text + alt_enter (ESC + CR) + enter (CR)
        assert writes[0] == b"line one\x1b\r\r"

    def test_text_only_no_submit_single_write(self) -> None:
        """Text without submit = single write with just text."""
        writes, _ = self._run_writer({"text": "just text"})
        assert len(writes) == 1
        assert writes[0] == b"just text"

    def test_submit_only_single_write(self) -> None:
        """Submit without text = single write with just enter."""
        writes, _ = self._run_writer({"submit": True})
        assert len(writes) == 1
        assert writes[0] == b"\r"

    def test_tcdrain_called_once(self) -> None:
        """tcdrain should be called exactly once per message."""
        _, drain_count = self._run_writer({"text": "hello\n", "submit": True})
        assert drain_count == 1
