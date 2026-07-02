"""Tests for PTYSession lifecycle: creation, cleanup, resize, and helpers.

Children are limited to `sh`/`cat` one-liners so every test stays fast and
deterministic.  Where run_output_loop() has an inherent race (waitpid WNOHANG
vs. read-EOF, see TestRunOutputLoop), the race is made deterministic by
patching os.waitpid so a single, known path is exercised.
"""

from __future__ import annotations

import contextlib
import os
import pty
import signal
import struct
import termios
from fcntl import ioctl
from unittest.mock import patch

import pytest

from dictare.agent.pty_session import (
    PTYSession,
    _get_winsize,
    _set_winsize,
    _write_all,
)


def _read_winsize(fd: int) -> tuple[int, int]:
    """Read (rows, cols) from a terminal fd via TIOCGWINSZ."""
    buf = struct.pack("HHHH", 0, 0, 0, 0)
    result = ioctl(fd, termios.TIOCGWINSZ, buf)
    rows, cols, _, _ = struct.unpack("HHHH", result)
    return rows, cols

def _reap(pid: int) -> None:
    """Kill and reap a child process, ignoring already-dead children."""
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)
    with contextlib.suppress(ChildProcessError):
        os.waitpid(pid, 0)

def _fd_is_closed(fd: int) -> bool:
    """True if fd is no longer a valid file descriptor."""
    try:
        os.fstat(fd)
        return False
    except OSError:
        return True

@pytest.fixture
def sigwinch_guard():
    """Snapshot the SIGWINCH handler and restore it after the test.

    Protects the test process even if a session leaks its handler.
    """
    old = signal.getsignal(signal.SIGWINCH)
    yield old
    signal.signal(signal.SIGWINCH, old)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestWinsizeHelpers:
    """_set_winsize / _get_winsize."""

    def test_set_winsize_roundtrip(self) -> None:
        """_set_winsize sets rows/cols readable via TIOCGWINSZ."""
        master_fd, slave_fd = pty.openpty()
        try:
            _set_winsize(slave_fd, 30, 90)
            assert _read_winsize(master_fd) == (30, 90)
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_set_winsize_closed_fd_does_not_raise(self) -> None:
        """_set_winsize swallows the OSError raised on a closed fd."""
        fd = os.open(os.devnull, os.O_RDONLY)
        os.close(fd)
        _set_winsize(fd, 24, 80)  # EBADF — must not raise

    def test_get_winsize_fallback_on_error(self) -> None:
        """_get_winsize returns (24, 80) when the ioctl fails."""
        with patch("dictare.agent.pty_session.ioctl", side_effect=OSError):
            assert _get_winsize() == (24, 80)

class TestWriteAll:
    """_write_all short-write handling."""

    def test_writes_all_bytes(self) -> None:
        """All bytes arrive on the other end of a pipe."""
        r, w = os.pipe()
        try:
            data = b"hello pty"
            assert _write_all(w, data) == len(data)
            assert os.read(r, 100) == data
        finally:
            os.close(r)
            os.close(w)

    def test_loops_on_short_writes(self) -> None:
        """os.write returning fewer bytes triggers a retry loop."""
        chunks: list[bytes] = []

        def short_write(fd: int, data: bytes) -> int:
            chunks.append(data[:2])
            return 2

        with patch("dictare.agent.pty_session.os.write", side_effect=short_write):
            assert _write_all(99, b"abcdef") == 6
        assert b"".join(chunks) == b"abcdef"

    def test_zero_write_raises(self) -> None:
        """os.write returning 0 raises OSError instead of spinning forever."""
        with patch("dictare.agent.pty_session.os.write", return_value=0):
            with pytest.raises(OSError, match="cannot make progress"):
                _write_all(99, b"abc")

# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

class TestSessionStartErrors:
    """Errors raised by start() before any fork happens."""

    def test_master_fd_before_start_raises(self) -> None:
        """Accessing master_fd before start() raises RuntimeError."""
        session = PTYSession(["cat"])
        with pytest.raises(RuntimeError, match="not started"):
            _ = session.master_fd

    def test_command_not_found_raises(self, sigwinch_guard) -> None:
        """A relative command missing from PATH raises FileNotFoundError."""
        session = PTYSession(["definitely-not-a-real-binary-xyz"])
        with pytest.raises(FileNotFoundError, match="Command not found"):
            session.start()
        # No handler was installed, no fd opened
        assert signal.getsignal(signal.SIGWINCH) is sigwinch_guard
        assert session._master_fd is None

class TestSessionCleanup:
    """cleanup() contract: restore SIGWINCH and close master_fd."""

    def test_cleanup_after_normal_start(self, sigwinch_guard) -> None:
        """After start() + cleanup(): fd closed, SIGWINCH restored."""
        session = PTYSession(["cat"], rows=25, cols=81)
        session.start()
        pid = session._pid
        assert pid is not None
        try:
            fd = session.master_fd
            # start() replaced the SIGWINCH handler
            assert signal.getsignal(signal.SIGWINCH) is not sigwinch_guard

            session.cleanup()

            assert signal.getsignal(signal.SIGWINCH) is sigwinch_guard
            assert _fd_is_closed(fd)
            assert session._master_fd is None
        finally:
            _reap(pid)

    def test_cleanup_after_exception_mid_session(self, sigwinch_guard) -> None:
        """cleanup() in a finally block restores state after a mid-session error."""
        session = PTYSession(["cat"])
        pid: int | None = None
        fd: int | None = None
        try:
            with pytest.raises(RuntimeError, match="boom"):
                try:
                    session.start()
                    pid = session._pid
                    fd = session.master_fd
                    raise RuntimeError("boom")  # Simulated mid-session failure
                finally:
                    session.cleanup()

            assert signal.getsignal(signal.SIGWINCH) is sigwinch_guard
            assert fd is not None and _fd_is_closed(fd)
        finally:
            if pid is not None:
                _reap(pid)

    def test_cleanup_is_idempotent(self, sigwinch_guard) -> None:
        """Calling cleanup() twice is safe."""
        session = PTYSession(["cat"])
        session.start()
        pid = session._pid
        assert pid is not None
        try:
            session.cleanup()
            session.cleanup()  # Must not raise
            assert signal.getsignal(signal.SIGWINCH) is sigwinch_guard
        finally:
            _reap(pid)

    def test_cleanup_before_start_is_noop(self, sigwinch_guard) -> None:
        """cleanup() on a never-started session does nothing."""
        session = PTYSession(["cat"])
        session.cleanup()
        assert signal.getsignal(signal.SIGWINCH) is sigwinch_guard

class TestResizePropagation:
    """SIGWINCH handler installed by start() propagates the new size."""

    def test_start_applies_initial_winsize(self, sigwinch_guard) -> None:
        """start() sets the requested rows/cols on the PTY."""
        session = PTYSession(["cat"], rows=31, cols=99)
        session.start()
        pid = session._pid
        assert pid is not None
        try:
            assert _read_winsize(session.master_fd) == (31, 99)
        finally:
            session.cleanup()
            _reap(pid)

    def test_sigwinch_handler_propagates_resize(self, sigwinch_guard) -> None:
        """Invoking the installed handler resizes the PTY and updates state."""
        session = PTYSession(["cat"], rows=24, cols=80)
        session.start()
        pid = session._pid
        assert pid is not None
        try:
            handler = signal.getsignal(signal.SIGWINCH)
            assert callable(handler)

            with patch(
                "dictare.agent.pty_session._get_winsize", return_value=(50, 120)
            ):
                handler(signal.SIGWINCH, None)

            assert _read_winsize(session.master_fd) == (50, 120)
            assert (session._rows, session._cols) == (50, 120)
        finally:
            session.cleanup()
            _reap(pid)

# ---------------------------------------------------------------------------
# Output loop
# ---------------------------------------------------------------------------

def _waitpid_read_path_wins(real_waitpid):
    """Fake os.waitpid forcing run_output_loop down the read-EOF exit path.

    WNOHANG polls report "still running" so the loop keeps reading until
    EOF (macOS) / EIO (Linux); the final blocking waitpid is real.
    """

    def fake(pid: int, flags: int):
        if flags == os.WNOHANG:
            return (0, 0)
        return real_waitpid(pid, flags)

    return fake

class TestRunOutputLoop:
    """run_output_loop(): output dispatch and exit-code reporting."""

    def test_output_and_exit_code_zero(self, sigwinch_guard) -> None:
        """Child output reaches on_output and exit code 0 is returned."""
        chunks: list[bytes] = []
        session = PTYSession(
            ["sh", "-c", "printf hello"], on_output=chunks.append
        )
        session.start()
        try:
            real_waitpid = os.waitpid
            with patch(
                "dictare.agent.pty_session.os.waitpid",
                side_effect=_waitpid_read_path_wins(real_waitpid),
            ):
                exit_code = session.run_output_loop()
            assert exit_code == 0
            assert b"hello" in b"".join(chunks)
        finally:
            session.cleanup()

    def test_nonzero_exit_code(self, sigwinch_guard) -> None:
        """Child exit code is propagated (read-EOF path)."""
        session = PTYSession(["sh", "-c", "exit 3"])
        session.start()
        try:
            real_waitpid = os.waitpid
            with patch(
                "dictare.agent.pty_session.os.waitpid",
                side_effect=_waitpid_read_path_wins(real_waitpid),
            ):
                assert session.run_output_loop() == 3
        finally:
            session.cleanup()

    def test_wnohang_reap_path_raises_childprocesserror(
        self, sigwinch_guard
    ) -> None:
        """KNOWN BUG (pinned): if the WNOHANG poll observes the child's exit
        first, the loop breaks and the final blocking waitpid raises
        ChildProcessError because the child was already reaped.

        In production this is a real race: probing 50 runs of a short-lived
        child hit it once.  Here the race is made deterministic by having the
        WNOHANG poll block until the child exits (reaping it), exactly what
        happens when the poll wins the race.  Do not "fix" this test without
        fixing run_output_loop's double waitpid.
        """
        session = PTYSession(["sh", "-c", "exit 0"])
        session.start()
        try:
            real_waitpid = os.waitpid

            def wnohang_wins(pid: int, flags: int):
                if flags == os.WNOHANG:
                    # Block until exit and reap — the WNOHANG poll "won".
                    return real_waitpid(pid, 0)
                return real_waitpid(pid, flags)

            with patch(
                "dictare.agent.pty_session.os.waitpid",
                side_effect=wnohang_wins,
            ):
                with pytest.raises(ChildProcessError):
                    session.run_output_loop()
        finally:
            session.cleanup()
