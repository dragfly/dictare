"""Tests for SSEAgent message delivery and mux status logic."""

from __future__ import annotations

import http.server
import json
import queue
import threading

from voxtype.agent.base import BaseAgent, OpenVIPMessage
from voxtype.agent.mux import _read_from_sse, _stream_active_agent
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


def _make_status_handler(agent_id: str, current_agent: str, state: str = "listening"):
    """Create an HTTP handler that serves /status JSON."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                body = json.dumps({
                    "platform": {
                        "state": state,
                        "output": {"current_agent": current_agent},
                    },
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


class TestStreamActiveAgentStatus:
    """Test _stream_active_agent status updates via SSE."""

    def _make_status(self, state: str, current_agent: str, agents: list[str] | None = None):
        """Create a mock Status object."""
        from openvip import Status

        return Status(
            protocol_version="1.0",
            state=state,
            connected_agents=agents or [current_agent],
            platform={
                "state": state,
                "output": {"current_agent": current_agent},
            },
        )

    def test_stream_shows_listening_when_active(self) -> None:
        """Active agent in listening state shows 'listening' (green)."""
        from unittest.mock import patch

        stop = threading.Event()
        statuses: list[tuple[str, str]] = []

        def on_status(text, style):
            statuses.append((text, style))
            stop.set()

        def fake_subscribe(**kwargs):
            yield self._make_status("listening", "myagent")

        with patch("openvip.Client") as mock_client:
            mock_client.return_value.subscribe_status.side_effect = fake_subscribe
            _stream_active_agent("myagent", "http://localhost:8770", stop, on_status)

        assert len(statuses) >= 1
        assert "listening" in statuses[0][0]
        assert statuses[0][1] == "ok"

    def test_stream_shows_idle_when_engine_off(self) -> None:
        """Active agent with engine idle shows 'idle' (dim)."""
        from unittest.mock import patch

        stop = threading.Event()
        statuses: list[tuple[str, str]] = []

        def on_status(text, style):
            statuses.append((text, style))
            stop.set()

        def fake_subscribe(**kwargs):
            yield self._make_status("idle", "myagent")

        with patch("openvip.Client") as mock_client:
            mock_client.return_value.subscribe_status.side_effect = fake_subscribe
            _stream_active_agent("myagent", "http://localhost:8770", stop, on_status)

        assert len(statuses) >= 1
        assert "idle" in statuses[0][0]
        assert statuses[0][1] == "dim"

    def test_stream_shows_standby_when_not_active(self) -> None:
        """Non-active agent shows 'standby' (warn)."""
        from unittest.mock import patch

        stop = threading.Event()
        statuses: list[tuple[str, str]] = []

        def on_status(text, style):
            statuses.append((text, style))
            stop.set()

        def fake_subscribe(**kwargs):
            yield self._make_status("listening", "other-agent")

        with patch("openvip.Client") as mock_client:
            mock_client.return_value.subscribe_status.side_effect = fake_subscribe
            _stream_active_agent("myagent", "http://localhost:8770", stop, on_status)

        assert len(statuses) >= 1
        assert "standby" in statuses[0][0]
        assert statuses[0][1] == "warn"

    def test_stream_deduplicates_same_status(self) -> None:
        """Repeated identical status does not trigger on_status again."""
        from unittest.mock import patch

        stop = threading.Event()
        statuses: list[tuple[str, str]] = []
        call_count = [0]

        def on_status(text, style):
            statuses.append((text, style))
            call_count[0] += 1
            if call_count[0] >= 2:
                stop.set()

        def fake_subscribe(**kwargs):
            # Yield same status twice — only first should trigger on_status
            yield self._make_status("listening", "myagent")
            yield self._make_status("listening", "myagent")
            # Yield different status to trigger second on_status and stop
            yield self._make_status("idle", "myagent")

        with patch("openvip.Client") as mock_client:
            mock_client.return_value.subscribe_status.side_effect = fake_subscribe
            _stream_active_agent("myagent", "http://localhost:8770", stop, on_status)

        assert len(statuses) == 2
        assert "listening" in statuses[0][0]
        assert "idle" in statuses[1][0]


    def test_stream_shows_starting_when_loading(self) -> None:
        """Engine loading models shows 'starting' (warn)."""
        from unittest.mock import patch

        from openvip import Status

        stop = threading.Event()
        statuses: list[tuple[str, str]] = []

        def on_status(text, style):
            statuses.append((text, style))
            stop.set()

        def fake_subscribe(**kwargs):
            yield Status(
                protocol_version="1.0",
                state="idle",
                connected_agents=[],
                platform={
                    "state": "idle",
                    "output": {"current_agent": None},
                    "loading": {"active": True},
                },
            )

        with patch("openvip.Client") as mock_client:
            mock_client.return_value.subscribe_status.side_effect = fake_subscribe
            _stream_active_agent("myagent", "http://localhost:8770", stop, on_status)

        assert len(statuses) >= 1
        assert "starting" in statuses[0][0]
        assert statuses[0][1] == "warn"


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


class TestSSEDisconnectStatus:
    """Test _read_from_sse reports disconnection errors via on_status."""

    def test_sse_error_reports_reconnecting(self) -> None:
        """SSE connection error triggers 'reconnecting' status."""
        stop = threading.Event()
        wq: queue.Queue = queue.Queue()
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

        def stop_after_reconnect():
            # Wait until we get at least one message (successful reconnect)
            while wq.empty() and call_count[0] < 3:
                threading.Event().wait(0.01)
            stop.set()

        threading.Thread(target=stop_after_reconnect, daemon=True).start()

        import unittest.mock as _mock
        with _mock.patch("urllib.request.urlopen", fake_urlopen), \
             _mock.patch("openvip.client.time.sleep"):
            _read_from_sse(
                "myagent",
                "http://127.0.0.1:9999",
                wq, stop,
                on_status=on_status,
            )

        error_statuses = [(t, s) for t, s in statuses if s == "error"]
        assert len(error_statuses) >= 1, f"Expected error status, got: {statuses}"


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
