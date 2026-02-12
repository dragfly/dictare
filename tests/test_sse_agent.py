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
        statuses: list[tuple[str, str]] = []
        handler = _make_status_handler("myagent", "myagent")

        # Get a free port, close immediately — first poll will fail
        temp = http.server.HTTPServer(("127.0.0.1", 0), handler)
        port = temp.server_address[1]
        temp.server_close()

        # Phase 1: poll once against closed port (error → was_active = None)
        stop1 = threading.Event()
        original_on_status_calls = [0]

        def on_status_phase1(text, style):
            # _poll_active_agent does NOT call on_status on error,
            # but we track calls to confirm none happen
            original_on_status_calls[0] += 1

        # Run one poll cycle — will fail on closed port, then stop
        def poll_once():
            _poll_active_agent("myagent", f"http://127.0.0.1:{port}", stop1,
                               on_status_phase1, poll_interval=0.001)

        pt = threading.Thread(target=poll_once, daemon=True)
        pt.start()
        # Give it a very short time then stop (poll_interval=0.001 is 1ms)
        stop1.set()
        pt.join(timeout=1)
        assert original_on_status_calls[0] == 0  # No status on error

        # Phase 2: start server, poll again — should force "listening"
        server2 = http.server.HTTPServer(("127.0.0.1", port), handler)
        t = threading.Thread(target=server2.handle_request, daemon=True)
        t.start()

        stop2 = threading.Event()

        def on_status_phase2(text, style):
            statuses.append((text, style))
            stop2.set()

        _poll_active_agent("myagent", f"http://127.0.0.1:{port}", stop2, on_status_phase2,
                           poll_interval=0.001)
        server2.server_close()

        assert len(statuses) >= 1
        assert "listening" in statuses[0][0]

class _FakeSSEResponse:
    """Fake HTTP response that yields SSE lines then stops."""

    def __init__(self, lines: list[str], stop_event: threading.Event) -> None:
        self._lines = iter(lines)
        self._stop = stop_event

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def __iter__(self):
        for line in self._lines:
            if self._stop.is_set():
                return
            yield line.encode("utf-8")
        # After all lines delivered, wait for stop to avoid retry loop
        self._stop.wait(timeout=1)

class TestSSEInputExecutorIntegration:
    """Test _read_from_sse processes x_input via InputExecutor."""

    _UUID1 = "550e8400-e29b-41d4-a716-446655440000"
    _UUID2 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    _UUID3 = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

    def test_submit_via_executor(self) -> None:
        """x_input with submit=True is processed by InputExecutor."""
        stop = threading.Event()
        wq: queue.Queue = queue.Queue()

        msg = json.dumps({
            "openvip": "1.0",
            "type": "transcription",
            "id": self._UUID1,
            "timestamp": "2026-01-01T00:00:00Z",
            "text": "hello",
            "x_input": {"submit": True},
        })
        fake_resp = _FakeSSEResponse([f"data: {msg}\n"], stop)

        def fake_urlopen(req, **kw):
            return fake_resp

        def stop_after_msg():
            while wq.empty():
                pass
            stop.set()

        threading.Thread(target=stop_after_msg, daemon=True).start()

        import unittest.mock as _mock
        with _mock.patch("urllib.request.urlopen", fake_urlopen):
            _read_from_sse("test", "http://127.0.0.1:9999", wq, stop)

        item = wq.get_nowait()
        assert item[0] == "msg"
        assert item[1]["text"] == "hello"
        assert item[1]["submit"] is True
        assert item[1]["openvip_id"] == self._UUID1

    def test_newline_via_executor(self) -> None:
        """x_input with newline=True appends \\n to text."""
        stop = threading.Event()
        wq: queue.Queue = queue.Queue()

        msg = json.dumps({
            "openvip": "1.0",
            "type": "transcription",
            "id": self._UUID2,
            "timestamp": "2026-01-01T00:00:00Z",
            "text": "line one",
            "x_input": {"newline": True},
        })
        fake_resp = _FakeSSEResponse([f"data: {msg}\n"], stop)

        def fake_urlopen(req, **kw):
            return fake_resp

        def stop_after_msg():
            while wq.empty():
                pass
            stop.set()

        threading.Thread(target=stop_after_msg, daemon=True).start()

        import unittest.mock as _mock
        with _mock.patch("urllib.request.urlopen", fake_urlopen):
            _read_from_sse("test", "http://127.0.0.1:9999", wq, stop)

        item = wq.get_nowait()
        assert item[0] == "msg"
        assert item[1]["text"] == "line one\n"

    def test_plain_text_no_executor(self) -> None:
        """Message without x_input passes through as plain text."""
        stop = threading.Event()
        wq: queue.Queue = queue.Queue()

        msg = json.dumps({
            "openvip": "1.0",
            "type": "transcription",
            "id": self._UUID3,
            "timestamp": "2026-01-01T00:00:00Z",
            "text": "plain text",
        })
        fake_resp = _FakeSSEResponse([f"data: {msg}\n"], stop)

        def fake_urlopen(req, **kw):
            return fake_resp

        def stop_after_msg():
            while wq.empty():
                pass
            stop.set()

        threading.Thread(target=stop_after_msg, daemon=True).start()

        import unittest.mock as _mock
        with _mock.patch("urllib.request.urlopen", fake_urlopen):
            _read_from_sse("test", "http://127.0.0.1:9999", wq, stop)

        item = wq.get_nowait()
        assert item[0] == "msg"
        assert item[1]["text"] == "plain text"
        assert item[1]["openvip_id"] == self._UUID3
        assert "submit" not in item[1]

class TestSSEConnectedEvent:
    """Test _read_from_sse signals sse_connected event (no direct status emit)."""

    def test_sse_connect_sets_event(self) -> None:
        """SSE connection success sets sse_connected event."""
        stop = threading.Event()
        wq: queue.Queue = queue.Queue()
        sse_connected = threading.Event()
        statuses: list[tuple[str, str]] = []

        def on_status(text, style):
            statuses.append((text, style))

        heartbeat = json.dumps({"type": "heartbeat"})
        fake_resp = _FakeSSEResponse([f"data: {heartbeat}\n"], stop)

        def fake_urlopen(req, **kw):
            return fake_resp

        def stop_when_connected():
            sse_connected.wait(timeout=1)
            stop.set()

        threading.Thread(target=stop_when_connected, daemon=True).start()

        import unittest.mock as _mock
        with _mock.patch("urllib.request.urlopen", fake_urlopen):
            _read_from_sse(
                "myagent",
                "http://127.0.0.1:9999",
                wq, stop,
                on_status=on_status,
                sse_connected=sse_connected,
            )

        assert sse_connected.is_set()
        ok_statuses = [(t, s) for t, s in statuses if "connected" in t]
        assert len(ok_statuses) == 0, f"SSE should not emit 'connected': {statuses}"

    def test_sse_error_then_reconnect_sets_event(self) -> None:
        """After SSE error, successful reconnect sets sse_connected event."""
        stop = threading.Event()
        wq: queue.Queue = queue.Queue()
        sse_connected = threading.Event()
        statuses: list[tuple[str, str]] = []
        call_count = [0]

        heartbeat = json.dumps({"type": "heartbeat"})

        def fake_urlopen(req, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionRefusedError("Connection refused")
            return _FakeSSEResponse([f"data: {heartbeat}\n"], stop)

        def on_status(text, style):
            statuses.append((text, style))

        def stop_when_connected():
            sse_connected.wait(timeout=2)
            stop.set()

        threading.Thread(target=stop_when_connected, daemon=True).start()

        import unittest.mock as _mock
        with _mock.patch("urllib.request.urlopen", fake_urlopen), \
             _mock.patch("openvip.client.time.sleep"):
            _read_from_sse(
                "myagent",
                "http://127.0.0.1:9999",
                wq, stop,
                on_status=on_status,
                sse_connected=sse_connected,
            )

        assert sse_connected.is_set()
        error_statuses = [(t, s) for t, s in statuses if s == "error"]
        assert len(error_statuses) >= 1, f"Expected error status, got: {statuses}"

    def test_poll_refreshes_on_sse_connected(self) -> None:
        """Poll thread re-emits status when sse_connected event is set."""
        statuses: list[tuple[str, str]] = []
        handler = _make_status_handler("myagent", "myagent")
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]

        stop = threading.Event()
        sse_connected = threading.Event()
        emit_count = [0]

        def on_status(text, style):
            statuses.append((text, style))
            emit_count[0] += 1
            if emit_count[0] == 1:
                # After first "listening" emit, set sse_connected to force refresh
                sse_connected.set()
            elif emit_count[0] == 2:
                # Second emit confirms poll re-emitted after sse_connected
                stop.set()

        # Serve enough requests for 2 poll cycles then stop
        def serve_requests():
            while not stop.is_set():
                server.handle_request()

        t = threading.Thread(target=serve_requests, daemon=True)
        t.start()

        _poll_active_agent(
            "myagent", f"http://127.0.0.1:{port}", stop, on_status,
            poll_interval=0.001, sse_connected=sse_connected,
        )
        server.server_close()

        # Should have emitted "listening" twice: initial + refresh after sse_connected
        assert emit_count[0] >= 2, f"Expected 2+ emits, got {emit_count[0]}: {statuses}"
        assert all("listening" in t for t, s in statuses), f"Unexpected statuses: {statuses}"

class TestSSEDuplicateAgent:
    """Test client behavior when server returns 409 (agent already connected)."""

    def test_409_stops_retry_and_reports_error(self) -> None:
        """HTTP 409 causes immediate exit with error, no retry loop."""
        import unittest.mock as _mock
        import urllib.error

        stop = threading.Event()
        wq: queue.Queue = queue.Queue()
        statuses: list[tuple[str, str]] = []
        call_count = [0]

        def fake_urlopen(req, **kw):
            call_count[0] += 1
            raise urllib.error.HTTPError(
                req.full_url, 409, "Conflict", {}, None,
            )

        def on_status(text, style):
            statuses.append((text, style))

        with _mock.patch("urllib.request.urlopen", fake_urlopen):
            _read_from_sse(
                "claude",
                "http://127.0.0.1:9999",
                wq, stop,
                on_status=on_status,
            )

        # Should have called urlopen exactly once (no retry)
        assert call_count[0] == 1

        # Should have reported error via status bar
        assert any("already connected" in t for t, s in statuses), f"Expected duplicate error, got: {statuses}"

        # Should have put error on write_queue
        assert not wq.empty()
        msg_type, data = wq.get_nowait()
        assert msg_type == "error"
        assert "already connected" in data

        # stop_event should NOT be set (SSE thread exits, child process continues)
        assert not stop.is_set()

    def test_other_http_errors_retry(self) -> None:
        """Non-409 HTTP errors still trigger retry with backoff."""
        import unittest.mock as _mock
        import urllib.error

        stop = threading.Event()
        wq: queue.Queue = queue.Queue()
        statuses: list[tuple[str, str]] = []
        call_count = [0]

        def fake_urlopen(req, **kw):
            call_count[0] += 1
            if call_count[0] >= 3:
                stop.set()
                raise urllib.error.HTTPError(
                    req.full_url, 500, "Internal Server Error", {}, None,
                )
            raise urllib.error.HTTPError(
                req.full_url, 500, "Internal Server Error", {}, None,
            )

        def on_status(text, style):
            statuses.append((text, style))

        with _mock.patch("urllib.request.urlopen", fake_urlopen), \
             _mock.patch("openvip.client.time.sleep"):
            _read_from_sse(
                "claude",
                "http://127.0.0.1:9999",
                wq, stop,
                on_status=on_status,
            )

        # Should have retried (more than 1 call)
        assert call_count[0] >= 2
        # Error statuses should mention HTTP code
        assert any("500" in t for t, s in statuses), f"Expected HTTP 500 in status, got: {statuses}"

class TestWriteToPtySeparateEsc:
    """Test that text and ESC sequences are written as SEPARATE os.write() calls.

    ESC (\x1b) in the same buffer as text confuses the slave's input parser,
    which treats ESC as the start of a key sequence and discards preceding text.
    """

    def _run_writer(self, data: dict) -> tuple[list[bytes], int]:
        """Helper: run _write_to_pty with one message, return (writes, drain_count)."""
        from unittest.mock import patch

        from voxtype.agent.mux import _write_to_pty

        wq: queue.Queue = queue.Queue()
        stop = threading.Event()
        writes: list[bytes] = []
        drain_count = [0]
        write_count = [0]

        def fake_write(fd, data_bytes):
            writes.append(data_bytes)
            write_count[0] += 1
            return len(data_bytes)

        def fake_tcdrain(fd):
            drain_count[0] += 1
            # Stop after all writes for this message are done
            # (tcdrain is called after each write segment)
            if not wq.qsize():
                stop.set()

        wq.put(("msg", data))

        with patch("os.write", side_effect=fake_write), \
             patch("termios.tcdrain", side_effect=fake_tcdrain):
            _write_to_pty(master_fd=99, write_queue=wq, stop_event=stop)

        return writes, drain_count[0]

    def test_text_with_submit_two_writes(self) -> None:
        """Text + submit: text in one write, enter in separate write."""
        writes, drains = self._run_writer({"text": "hello world", "submit": True})
        assert len(writes) == 2
        assert writes[0] == b"hello world"
        assert writes[1] == b"\r"
        assert drains == 2

    def test_text_with_visual_newline_three_writes(self) -> None:
        """Text + visual newline + submit: three separate writes."""
        writes, drains = self._run_writer({"text": "line one\n", "submit": True})
        assert len(writes) == 3
        assert writes[0] == b"line one"       # text (no ESC)
        assert writes[1] == b"\x1b\r"         # alt_enter (ESC — separate!)
        assert writes[2] == b"\r"             # enter
        assert drains == 3

    def test_text_only_one_write(self) -> None:
        """Text without newline or submit = single write."""
        writes, drains = self._run_writer({"text": "just text"})
        assert len(writes) == 1
        assert writes[0] == b"just text"
        assert drains == 1

    def test_submit_only_one_write(self) -> None:
        """Submit without text = single write with just enter."""
        writes, drains = self._run_writer({"submit": True})
        assert len(writes) == 1
        assert writes[0] == b"\r"
        assert drains == 1

    def test_text_never_contains_esc(self) -> None:
        """The text write must NEVER contain ESC byte."""
        writes, _ = self._run_writer({"text": "hello world\n", "submit": True})
        text_write = writes[0]
        assert b"\x1b" not in text_write, f"Text write contains ESC: {text_write!r}"
