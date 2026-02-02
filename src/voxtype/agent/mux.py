"""Agent multiplexer - run commands with merged stdin and voxtype input."""

from __future__ import annotations

import json
import os
import platform
import pty
import queue
import select
import signal
import socket
import struct
import sys
import termios
import threading
import time
import tty
from datetime import datetime, timezone
from fcntl import ioctl
from pathlib import Path
from typing import Any

from voxtype import __version__
from voxtype.utils.stats import update_keystrokes

# Session logs directory
SESSIONS_DIR = Path.home() / ".local" / "share" / "voxtype" / "sessions"


def get_socket_path(agent_id: str) -> Path:
    """Get Unix socket path for an agent.

    Args:
        agent_id: Agent identifier.

    Returns:
        Path to socket file in the platform-appropriate runtime directory.
    """
    from voxtype.utils.platform import get_socket_dir

    return get_socket_dir() / f"{agent_id}.sock"


def _get_session_log_path(agent_id: str) -> Path:
    """Get path for session log file.

    Format: YYYY-MM-DD_HH-MM-SS_voxtype-X.Y.Z_AGENT.session.jsonl
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{timestamp}_voxtype-{__version__}_{agent_id}.session.jsonl"
    return SESSIONS_DIR / filename


def _write_session_start(
    session_path: Path,
    agent_id: str,
    command: list[str],
    socket_path: Path,
) -> None:
    """Write session start metadata to log file."""
    metadata = {
        "event": "session_start",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "voxtype_version": __version__,
        "agent_id": agent_id,
        "command": command,
        "socket_path": str(socket_path),
        "cwd": os.getcwd(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "platform_version": platform.release(),
        "user": os.environ.get("USER", "unknown"),
        "shell": os.environ.get("SHELL", "unknown"),
        "term": os.environ.get("TERM", "unknown"),
    }
    with open(session_path, "a") as f:
        f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        f.flush()


def _write_session_end(
    session_path: Path, exit_code: int, total_keystrokes: int = 0
) -> None:
    """Write session end event to log file."""
    metadata = {
        "event": "session_end",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "exit_code": exit_code,
        "total_keystrokes": total_keystrokes,
    }
    with open(session_path, "a") as f:
        f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        f.flush()


def _log_event(session_path: Path, event: str, data: dict) -> None:
    """Log an event to the session log file (thread-safe)."""
    try:
        log_entry = {
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        with open(session_path, "a") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            f.flush()
    except OSError:
        pass  # Don't crash if logging fails




class KeystrokeCounter:
    """Thread-safe keystroke counter for session statistics."""

    def __init__(self) -> None:
        self._count = 0
        self._lock = threading.Lock()

    def add(self, n: int) -> None:
        with self._lock:
            self._count += n

    @property
    def count(self) -> int:
        with self._lock:
            return self._count


def _read_from_stdin(
    write_queue: queue.Queue,
    stop_event: threading.Event,
    keystroke_counter: KeystrokeCounter | None = None,
) -> None:
    """Read from keyboard in raw mode and put data in queue."""
    try:
        while not stop_event.is_set():
            r, _, _ = select.select([sys.stdin.fileno()], [], [], 0.1)
            if sys.stdin.fileno() in r:
                data = os.read(sys.stdin.fileno(), 1024)
                if not data:
                    break
                # Count keystrokes (bytes received = approximate keystroke count)
                if keystroke_counter:
                    keystroke_counter.add(len(data))
                # Put raw bytes directly in queue
                write_queue.put(("raw", data))
    except (BrokenPipeError, OSError):
        pass


def _read_from_socket(
    socket_path: Path,
    write_queue: queue.Queue,
    stop_event: threading.Event,
    session_path: Path | None = None,
    keystroke_counter: KeystrokeCounter | None = None,
    verbose: bool = False,
) -> None:
    """Listen on Unix socket for OpenVIP messages.

    Receives OpenVIP messages and converts to internal format:
    - {"type": "message", "text": "hello", "x_submit": true} -> {"text": "hello", "submit": true}
    - {"type": "message", "text": "\\n", "x_visual_newline": true} -> {"text": "\\n"}
    """
    msg_count = 0

    # Remove stale socket file
    if socket_path.exists():
        socket_path.unlink()

    # Create Unix socket server
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(str(socket_path))
    server.listen(5)
    server.setblocking(False)

    try:
        while not stop_event.is_set():
            # Check for new connections with timeout
            try:
                ready, _, _ = select.select([server], [], [], 0.1)
            except (ValueError, OSError):
                break

            if not ready:
                continue

            try:
                conn, _ = server.accept()
            except BlockingIOError:
                continue

            # Read data from connection
            try:
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                conn.close()
            except OSError:
                continue

            # Parse OpenVIP message(s) - one per line
            for line in data.decode("utf-8").strip().split("\n"):
                if not line:
                    continue

                try:
                    openvip_msg = json.loads(line)
                except json.JSONDecodeError:
                    if session_path:
                        _log_event(session_path, "parse_error", {"line": line[:100]})
                    continue

                # Skip non-message types
                if openvip_msg.get("type") != "message":
                    continue

                # Convert OpenVIP to internal format, preserving metadata for tracing
                msg: dict[str, Any] = {
                    "text": openvip_msg.get("text", ""),
                    "openvip_id": openvip_msg.get("id"),
                    "openvip_ts": openvip_msg.get("timestamp"),
                }
                if openvip_msg.get("x_submit"):
                    msg["submit"] = True
                if openvip_msg.get("x_visual_newline"):
                    msg["text"] = msg["text"] + "\n" if msg["text"] else "\n"

                msg_count += 1
                if session_path:
                    text = msg.get("text", "")
                    _log_event(session_path, "msg_read", {
                        "seq": msg_count,
                        "text": text if verbose else text[:50],
                        "openvip_id": openvip_msg.get("id"),
                        "keystrokes": keystroke_counter.count if keystroke_counter else 0,
                    })

                write_queue.put(("msg", msg))

    except (BrokenPipeError, OSError) as e:
        if session_path:
            _log_event(session_path, "reader_error", {"error": str(e)})
    finally:
        server.close()
        if socket_path.exists():
            socket_path.unlink()


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


def _write_to_pty(
    master_fd: int,
    write_queue: queue.Queue,
    stop_event: threading.Event,
    session_path: Path | None = None,
    keystroke_counter: KeystrokeCounter | None = None,
    verbose: bool = False,
) -> None:
    """Consume from queue and write to PTY.

    This is the ONLY thread that writes to master_fd, ensuring serialization.
    Logs every message sent for debugging.
    """
    # Alt+Enter for visual newline (ESC + CR)
    alt_enter = b"\x1b\r"
    enter_key = b"\r"
    msg_count = 0

    while not stop_event.is_set():
        try:
            # Block with timeout so we can check stop_event
            item = write_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        msg_type, data = item

        try:
            if msg_type == "raw":
                # Raw bytes from stdin - write directly, handle short writes
                _write_all(master_fd, data)
            elif msg_type == "msg":
                msg_count += 1
                # Parsed JSONL message from file
                text = data.get("text", "")
                bytes_written = 0

                if text:
                    has_visual_newline = text.endswith("\n")
                    if has_visual_newline:
                        text = text.rstrip("\n")

                    if text:
                        text_bytes = text.encode()
                        bytes_written += _write_all(master_fd, text_bytes)
                        # Drain to ensure bytes reach slave side
                        termios.tcdrain(master_fd)
                        time.sleep(0.1)  # 100ms delay for Claude Code to process

                    # Send Alt+Enter for visual newline
                    if has_visual_newline:
                        bytes_written += _write_all(master_fd, alt_enter)
                        termios.tcdrain(master_fd)
                        time.sleep(0.1)  # 100ms delay

                # Handle submit flag
                if data.get("submit"):
                    time.sleep(0.01)
                    bytes_written += _write_all(master_fd, enter_key)
                    termios.tcdrain(master_fd)

                # Log message AFTER successful write AND drain
                if session_path:
                    text = data.get("text", "")
                    _log_event(session_path, "msg_sent", {
                        "seq": msg_count,
                        "text": text if verbose else text[:50],
                        "bytes": bytes_written,
                        "openvip_id": data.get("openvip_id"),
                        "openvip_ts": data.get("openvip_ts"),
                        "keystrokes": keystroke_counter.count if keystroke_counter else 0,
                    })
        except (BrokenPipeError, OSError) as e:
            if session_path:
                _log_event(session_path, "writer_error", {"error": str(e), "msg_count": msg_count})
            break


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


def _is_socket_active(socket_path: Path) -> bool:
    """Check if a socket has an active listener.

    Args:
        socket_path: Path to the Unix socket.

    Returns:
        True if there's an active listener, False if socket is stale or doesn't exist.
    """
    if not socket_path.exists():
        return False

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            sock.connect(str(socket_path))
        # Connection succeeded - there's an active listener
        return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        # No listener or socket is stale
        return False


def run_agent(
    agent_id: str,
    command: list[str],
    quiet: bool = False,
    verbose: bool = False,
) -> int:
    """Run a command with multiplexed input from stdin and voxtype.

    Listens on a Unix socket for OpenVIP messages from voxtype listen.

    Args:
        agent_id: Agent identifier (e.g., 'claude').
        command: Command and arguments to run.
        quiet: Suppress info messages.
        verbose: Log full text in session file (not truncated to 50 chars).

    Returns:
        Exit code of the process.
    """
    # Get socket path for this agent
    socket_path = get_socket_path(agent_id)

    # Check if another agent with the same ID is already running
    if _is_socket_active(socket_path):
        print(
            f"Error: Agent '{agent_id}' is already running.",
            file=sys.stderr,
        )
        print(
            f"Socket in use: {socket_path}",
            file=sys.stderr,
        )
        print(
            "Use a different agent ID or stop the existing agent first.",
            file=sys.stderr,
        )
        return 1

    # Register cleanup handler (safety net for abnormal exits)
    import atexit

    def cleanup_socket():
        if socket_path.exists():
            try:
                socket_path.unlink()
            except OSError:
                pass

    atexit.register(cleanup_socket)

    # Create session log
    session_path = _get_session_log_path(agent_id)
    _write_session_start(session_path, agent_id, command, socket_path)

    if not quiet:
        print(f"[voxtype {__version__}] Agent: {agent_id}", file=sys.stderr)
        print(f"[voxtype {__version__}] Socket: {socket_path}", file=sys.stderr)
        print(f"[voxtype {__version__}] Session: {session_path}", file=sys.stderr)
        print(f"[voxtype {__version__}] Running: {' '.join(command)}", file=sys.stderr)

    # Save original terminal settings
    old_settings = None
    if sys.stdin.isatty():
        old_settings = termios.tcgetattr(sys.stdin.fileno())

    # Create pseudo-terminal
    master_fd, slave_fd = pty.openpty()

    # Set initial window size
    rows, cols = _get_winsize()
    _set_winsize(slave_fd, rows, cols)

    stop_event = threading.Event()

    # Handle window resize
    def handle_sigwinch(signum, frame):
        rows, cols = _get_winsize()
        _set_winsize(master_fd, rows, cols)

    old_sigwinch = signal.signal(signal.SIGWINCH, handle_sigwinch)

    try:
        # Fork process with PTY
        pid = os.fork()

        if pid == 0:
            # Child process
            os.close(master_fd)
            os.setsid()

            # Set slave as controlling terminal
            ioctl(slave_fd, termios.TIOCSCTTY, 0)

            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)

            if slave_fd > 2:
                os.close(slave_fd)

            os.execvp(command[0], command)

        # Parent process
        os.close(slave_fd)

        # Put terminal in raw mode
        if old_settings:
            tty.setraw(sys.stdin.fileno())

        # Create thread-safe queue for serialized writes to PTY
        # This prevents race conditions between stdin and socket input
        write_queue: queue.Queue = queue.Queue()

        # Create keystroke counter for session statistics
        keystroke_counter = KeystrokeCounter()

        # Start producer threads (read from stdin/socket, put in queue)
        stdin_thread = threading.Thread(
            target=_read_from_stdin,
            args=(write_queue, stop_event, keystroke_counter),
            daemon=True,
        )
        socket_thread = threading.Thread(
            target=_read_from_socket,
            args=(socket_path, write_queue, stop_event, session_path, keystroke_counter, verbose),
            daemon=True,
        )
        # Start consumer thread (read from queue, write to PTY)
        writer_thread = threading.Thread(
            target=_write_to_pty,
            args=(master_fd, write_queue, stop_event, session_path, keystroke_counter, verbose),
            daemon=True,
        )

        stdin_thread.start()
        socket_thread.start()
        writer_thread.start()

        # Read from PTY and write to stdout
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
                            os.write(sys.stdout.fileno(), data)
                        else:
                            break
                    except OSError:
                        break
        except KeyboardInterrupt:
            os.kill(pid, signal.SIGTERM)

        # Wait for child and get exit status
        _, status = os.waitpid(pid, 0)
        stop_event.set()

        if os.WIFEXITED(status):
            exit_code = os.WEXITSTATUS(status)
        else:
            exit_code = 1

        # Log session end with total keystrokes
        _write_session_end(session_path, exit_code, keystroke_counter.count)

        # Update lifetime stats with keystroke count
        if keystroke_counter.count > 0:
            update_keystrokes(keystroke_counter.count)
        return exit_code

    finally:
        # Clean up socket file (daemon threads don't run finally blocks on exit)
        if socket_path.exists():
            try:
                socket_path.unlink()
            except OSError:
                pass

        # Restore terminal settings
        if old_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

        signal.signal(signal.SIGWINCH, old_sigwinch)

        try:
            os.close(master_fd)
        except OSError:
            pass
