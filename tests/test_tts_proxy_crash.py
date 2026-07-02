"""Tests for WorkerTTSEngine behavior when the TTS worker subprocess dies.

Contract under test (read from src/dictare/tts/proxy.py and
src/dictare/core/tts_manager.py):

- Worker never connected / already dead: put_message() returns False and
  speak() returns False immediately (dropped with a warning, no hang).
- Worker dies AFTER a message was delivered: no completion ever arrives, so
  speak() blocks until _SPEAK_TIMEOUT, then returns False and cleans up its
  pending entry.
- There is NO automatic respawn: neither the proxy nor TTSManager monitors
  the worker process after spawn.  Subsequent speak() calls simply fail
  (put_message False) until a new engine load spawns a fresh worker.
- Late/unknown completions (after timeout) are ignored without error.

The server is mocked — no HTTP, no subprocesses, no audio.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import dictare.core.engine  # noqa: F401 — pre-import: speak() imports it lazily
from dictare.tts.proxy import WorkerTTSEngine


def _make_proxy(*, delivered: bool) -> tuple[WorkerTTSEngine, MagicMock]:
    """Build a proxy over a mock server whose put_message returns *delivered*."""
    server = MagicMock()
    server.put_message.return_value = delivered
    return WorkerTTSEngine(server), server

class TestWorkerNotConnected:
    """Worker dead before delivery: speak() fails fast."""

    def test_speak_returns_false_immediately(self) -> None:
        """put_message False → speak returns False without waiting."""
        proxy, _ = _make_proxy(delivered=False)

        start = time.monotonic()
        assert proxy.speak("hello") is False
        # Fail-fast: nowhere near the 120s speak timeout
        assert time.monotonic() - start < 0.5

    def test_no_pending_entry_leaks(self) -> None:
        """The pending-request map is cleaned up on drop."""
        proxy, _ = _make_proxy(delivered=False)
        proxy.speak("hello")
        assert proxy._pending == {}

    def test_is_available_reflects_server(self) -> None:
        """is_available() delegates to the server's TTS connection state."""
        proxy, server = _make_proxy(delivered=False)
        server.is_tts_connected.return_value = False
        assert proxy.is_available() is False
        server.is_tts_connected.return_value = True
        assert proxy.is_available() is True

class TestWorkerDiesAfterDelivery:
    """Worker crashes after the message was queued: speak() times out cleanly."""

    def test_speak_times_out_and_returns_false(self) -> None:
        """No completion ever arrives → speak returns False after the timeout."""
        proxy, _ = _make_proxy(delivered=True)

        with patch("dictare.tts.proxy._SPEAK_TIMEOUT", 0.05):
            start = time.monotonic()
            assert proxy.speak("hello") is False
            elapsed = time.monotonic() - start

        # Waited for the (patched) timeout, then gave up — no hang
        assert 0.05 <= elapsed < 1.0
        assert proxy._pending == {}

    def test_late_completion_after_timeout_is_ignored(self) -> None:
        """A completion for a timed-out (unknown) message id is a no-op."""
        proxy, server = _make_proxy(delivered=True)

        with patch("dictare.tts.proxy._SPEAK_TIMEOUT", 0.05):
            proxy.speak("hello")

        # Recover the message id the proxy generated for the dropped request
        message_id = server.put_message.call_args[0][1]["id"]
        proxy.complete(message_id, ok=True, duration_ms=42)  # Must not raise
        assert proxy._pending == {}

    def test_subsequent_speak_does_not_respawn_worker(self) -> None:
        """After a crash there is no respawn: the proxy only retries delivery.

        Pins the current design: WorkerTTSEngine owns no subprocess handle and
        never restarts the worker — a dead worker means speak() keeps failing
        until TTSManager spawns a new one on the next engine load.
        """
        proxy, server = _make_proxy(delivered=True)

        with patch("dictare.tts.proxy._SPEAK_TIMEOUT", 0.05):
            proxy.speak("first")  # times out (worker died mid-flight)

        server.put_message.return_value = False  # worker now fully gone
        assert proxy.speak("second") is False

        # Only delivery attempts were made — no other server interaction
        assert server.put_message.call_count == 2
        assert all(name == "put_message" for name, _, _ in server.method_calls)

class TestCompletionPath:
    """Sanity check: a live worker completing the request unblocks speak()."""

    def test_completion_from_another_thread_unblocks_speak(self) -> None:
        """complete() posted by the worker thread makes speak() return ok."""
        proxy, server = _make_proxy(delivered=True)

        def complete_soon() -> None:
            # Wait until speak() has registered its pending entry
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and not proxy._pending:
                time.sleep(0.001)
            (message_id,) = list(proxy._pending)
            proxy.complete(message_id, ok=True, duration_ms=10)

        worker = threading.Thread(target=complete_soon, daemon=True)
        worker.start()
        try:
            assert proxy.speak("hello") is True
        finally:
            worker.join(timeout=2.0)
        assert proxy._pending == {}

    def test_worker_failure_result_is_propagated(self) -> None:
        """complete(ok=False) makes speak() return False (not a timeout)."""
        proxy, server = _make_proxy(delivered=True)

        def fail_soon() -> None:
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and not proxy._pending:
                time.sleep(0.001)
            (message_id,) = list(proxy._pending)
            proxy.complete(message_id, ok=False)

        worker = threading.Thread(target=fail_soon, daemon=True)
        worker.start()
        try:
            assert proxy.speak("hello") is False
        finally:
            worker.join(timeout=2.0)
