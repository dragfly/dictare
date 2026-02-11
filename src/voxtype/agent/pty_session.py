"""PTY session — manages a child process inside a pseudo-terminal."""

from __future__ import annotations

import os
import pty
import select
import signal
import struct
import sys
import termios
from collections.abc import Callable
from fcntl import ioctl

def _set_winsize(fd: int, rows: int, cols: int) -> None:
    """Set terminal window size."""
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        ioctl(fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        pass

def _get_winsize() -> tuple[int, int]:
    """Get current terminal window size."""
    try:
        winsize = struct.pack("HHHH", 0, 0, 0, 0)
        result = ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, winsize)
        rows, cols, _, _ = struct.unpack("HHHH", result)
        return rows, cols
    except OSError:
        return 24, 80

def _write_all(fd: int, data: bytes) -> int:
    """Write all bytes to fd, handling short writes.

    os.write() can return fewer bytes than requested if the buffer is full.
    This function loops until all bytes are written.

    Returns total bytes written, raises on error.
    """
    total_written = 0
    while total_written < len(data):
        written = os.write(fd, data[total_written:])
        if written == 0:
            raise OSError("write() returned 0 - cannot make progress")
        total_written += written
    return total_written

class PTYSession:
    """Manages a child process inside a pseudo-terminal.

    Handles: openpty, fork+exec, SIGWINCH, output loop, waitpid, cleanup.
    Does NOT handle: raw mode, status bar, SSE, session logging, write queue.
    """

    def __init__(
        self,
        command: list[str],
        rows: int = 24,
        cols: int = 80,
        on_output: Callable[[bytes], None] | None = None,
        on_resize: Callable[[int, int], None] | None = None,
        reserve_rows: int = 0,
    ) -> None:
        self._command = command
        self._rows = rows
        self._cols = cols
        self._on_output = on_output
        self._on_resize = on_resize
        self._reserve_rows = reserve_rows
        self._master_fd: int | None = None
        self._pid: int | None = None
        self._old_sigwinch: signal._HANDLER | None = None

    @property
    def master_fd(self) -> int:
        """File descriptor for the master side of the PTY."""
        if self._master_fd is None:
            raise RuntimeError("PTYSession not started")
        return self._master_fd

    def start(self) -> None:
        """Open PTY, set window size, install SIGWINCH handler, fork+exec."""
        master_fd, slave_fd = pty.openpty()
        _set_winsize(slave_fd, self._rows - self._reserve_rows, self._cols)

        # Install SIGWINCH handler before fork
        def _handle_sigwinch(signum: int, frame: object) -> None:
            rows, cols = _get_winsize()
            self._rows = rows
            self._cols = cols
            if self._on_resize:
                self._on_resize(rows, cols)
            _set_winsize(master_fd, rows - self._reserve_rows, cols)

        self._old_sigwinch = signal.signal(signal.SIGWINCH, _handle_sigwinch)

        pid = os.fork()

        if pid == 0:
            # Child process
            os.close(master_fd)
            os.setsid()
            ioctl(slave_fd, termios.TIOCSCTTY, 0)
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.execvp(self._command[0], self._command)

        # Parent process
        os.close(slave_fd)
        self._master_fd = master_fd
        self._pid = pid

    def run_output_loop(self, on_idle: Callable[[], None] | None = None) -> int:
        """Read from PTY and dispatch output. Blocks until child exits.

        Args:
            on_idle: Called on each select timeout (e.g. for deferred redraws).

        Returns:
            Child process exit code.
        """
        master_fd = self.master_fd
        pid = self._pid
        assert pid is not None

        try:
            while True:
                result = os.waitpid(pid, os.WNOHANG)
                if result[0] != 0:
                    break

                r, _, _ = select.select([master_fd], [], [], 0.1)
                if master_fd in r:
                    try:
                        data = os.read(master_fd, 4096)
                        if data:
                            if self._on_output:
                                self._on_output(data)
                        else:
                            break
                    except OSError:
                        break

                if on_idle:
                    on_idle()
        except KeyboardInterrupt:
            os.kill(pid, signal.SIGTERM)

        # Wait for child and get exit status
        _, status = os.waitpid(pid, 0)
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        return 1

    def cleanup(self) -> None:
        """Restore SIGWINCH and close master_fd. Idempotent."""
        if self._old_sigwinch is not None:
            signal.signal(signal.SIGWINCH, self._old_sigwinch)
            self._old_sigwinch = None

        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
