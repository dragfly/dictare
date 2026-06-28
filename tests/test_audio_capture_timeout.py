"""Tests for the PortAudio call timeout watchdog in audio.capture.

These guard the audio-reconnect hang fix: a blocking PortAudio C call must
never wedge the caller forever. See _run_with_timeout.
"""

from __future__ import annotations

import threading
import time

import pytest

from dictare.audio.capture import _abort_close_stream, _run_with_timeout


def test_returns_result_when_call_is_fast() -> None:
    result = _run_with_timeout(lambda: 42, timeout_s=1.0, label="fast")
    assert result == 42


def test_propagates_exception_from_call() -> None:
    def _boom() -> None:
        raise ValueError("device gone")

    with pytest.raises(ValueError, match="device gone"):
        _run_with_timeout(_boom, timeout_s=1.0, label="boom")


def test_raises_timeout_instead_of_hanging() -> None:
    """A call that blocks past the timeout must not wedge the caller."""
    started = time.monotonic()

    def _wedge() -> str:
        time.sleep(5.0)  # simulate a stuck Pa_OpenStream
        return "too late"

    with pytest.raises(TimeoutError):
        _run_with_timeout(_wedge, timeout_s=0.1, label="wedge")

    # We returned promptly, nowhere near the 5s block.
    assert time.monotonic() - started < 1.0


def test_on_late_cleans_up_abandoned_result() -> None:
    """When an abandoned call eventually returns, on_late reaps its result."""
    reaped = threading.Event()
    captured: list[object] = []

    def _slow() -> str:
        time.sleep(0.2)
        return "stream-object"

    def _on_late(result: object) -> None:
        captured.append(result)
        reaped.set()

    with pytest.raises(TimeoutError):
        _run_with_timeout(_slow, timeout_s=0.05, label="slow", on_late=_on_late)

    assert reaped.wait(timeout=2.0), "on_late was never invoked for the late result"
    assert captured == ["stream-object"]


def test_abort_close_stream_swallows_errors() -> None:
    class _BadStream:
        def abort(self) -> None:
            raise RuntimeError("abort failed")

        def close(self) -> None:
            raise RuntimeError("close failed")

    # Must not raise even when both calls fail.
    _abort_close_stream(_BadStream())
    _abort_close_stream(None)
