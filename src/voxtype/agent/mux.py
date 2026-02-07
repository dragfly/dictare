"""Agent multiplexer - run commands with merged stdin and voxtype input."""

from __future__ import annotations

import json
import os
import platform
import pty
import queue
import select
import signal
import struct
import sys
import termios
import threading
import time
import tty
from collections.abc import Callable
from datetime import datetime, timezone
from fcntl import ioctl
from pathlib import Path
from typing import Any

from voxtype import __version__
from voxtype.agent.status_bar import StatusBar
from voxtype.utils.stats import update_keystrokes

# Session logs directory
SESSIONS_DIR = Path.home() / ".local" / "share" / "voxtype" / "sessions"

# Default engine HTTP server URL (also configurable via [client] in config.toml)
DEFAULT_BASE_URL = "http://127.0.0.1:8765"


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
    base_url: str,
) -> None:
    """Write session start metadata to log file."""
    metadata = {
        "event": "session_start",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "voxtype_version": __version__,
        "agent_id": agent_id,
        "command": command,
        "base_url": base_url,
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


def _read_from_sse(
    agent_id: str,
    base_url: str,
    write_queue: queue.Queue,
    stop_event: threading.Event,
    session_path: Path | None = None,
    keystroke_counter: KeystrokeCounter | None = None,
    verbose: bool = False,
    on_status: Callable[[str], None] | None = None,
) -> None:
    """Connect to engine SSE and receive OpenVIP messages.

    Opens an HTTP connection to GET /agents/{agent_id}/messages which
    registers the agent and streams messages via Server-Sent Events.

    Args:
        agent_id: Agent identifier.
        base_url: Engine HTTP server base URL (e.g. "http://127.0.0.1:8765").
        write_queue: Queue for writing messages to PTY.
        stop_event: Event to signal thread to stop.
        session_path: Optional session log file path.
        keystroke_counter: Optional keystroke counter for session stats.
        verbose: Log full text in session file.
        on_status: Optional callback for status changes (connected/reconnecting).
    """
    import urllib.request

    msg_count = 0
    url = f"{base_url}/agents/{agent_id}/messages"

    # Retry connection with backoff
    retry_delay = 0.5
    max_retry_delay = 5.0

    while not stop_event.is_set():
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "text/event-stream"}
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                if session_path:
                    _log_event(session_path, "sse_connected", {"url": url})
                retry_delay = 0.5  # Reset backoff on successful connection
                if on_status:
                    on_status(f"\u25cf {agent_id} \u00b7 connected", "ok")

                for line_bytes in response:
                    if stop_event.is_set():
                        break

                    line = line_bytes.decode("utf-8").strip()

                    # SSE format: "data: {...json...}"
                    if not line.startswith("data: "):
                        continue

                    data = line[6:]
                    try:
                        openvip_msg = json.loads(data)
                    except json.JSONDecodeError:
                        if session_path:
                            _log_event(session_path, "parse_error", {"line": data[:100]})
                        continue

                    # Skip non-transcription types
                    if openvip_msg.get("type") != "transcription":
                        continue

                    # Skip partial transcriptions
                    if openvip_msg.get("partial"):
                        continue

                    # Convert OpenVIP to internal format
                    msg: dict[str, Any] = {
                        "text": openvip_msg.get("text", ""),
                        "openvip_id": openvip_msg.get("id"),
                        "openvip_ts": openvip_msg.get("timestamp"),
                    }
                    x_input = openvip_msg.get("x_input", {})
                    if isinstance(x_input, dict) and x_input.get("submit"):
                        msg["submit"] = True
                    if isinstance(x_input, dict) and x_input.get("newline"):
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

        except (ConnectionRefusedError, urllib.error.URLError, OSError) as e:
            if stop_event.is_set():
                break
            if on_status:
                on_status(f"\u26a0 {agent_id} \u00b7 reconnecting...", "error")
            if session_path:
                _log_event(session_path, "sse_connect_error", {
                    "error": str(e), "retry_delay": retry_delay,
                })
            # Wait before retry with exponential backoff
            stop_event.wait(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)
        except Exception as e:
            if session_path:
                _log_event(session_path, "sse_error", {"error": str(e)})
            if stop_event.is_set():
                break
            if on_status:
                on_status(f"\u26a0 {agent_id} \u00b7 reconnecting...", "error")
            stop_event.wait(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)

    if session_path:
        _log_event(session_path, "sse_disconnected", {"total_messages": msg_count})


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


def run_agent(
    agent_id: str,
    command: list[str],
    quiet: bool = False,
    verbose: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    status_bar: bool = True,
    clear_on_start: bool = True,
) -> int:
    """Run a command with multiplexed input from stdin and voxtype SSE.

    Connects to the engine's HTTP server via SSE to receive OpenVIP messages.
    The SSE connection itself registers the agent with the engine.

    Args:
        agent_id: Agent identifier (e.g., 'claude').
        command: Command and arguments to run.
        quiet: Suppress info messages.
        verbose: Log full text in session file (not truncated to 50 chars).
        base_url: Engine HTTP server base URL.
        status_bar: Show persistent status bar on last terminal row.
        clear_on_start: Clear terminal before launching child process.

    Returns:
        Exit code of the process.
    """
    # Create session log
    session_path = _get_session_log_path(agent_id)
    _write_session_start(session_path, agent_id, command, base_url)

    if not quiet:
        print(f"[voxtype {__version__}] Agent: {agent_id}", file=sys.stderr)
        print(f"[voxtype {__version__}] Server: {base_url}", file=sys.stderr)
        print(f"[voxtype {__version__}] Session: {session_path}", file=sys.stderr)
        print(f"[voxtype {__version__}] Running: {' '.join(command)}", file=sys.stderr)

    # Health check: verify server is reachable before starting subprocess
    import urllib.error
    import urllib.request

    status_url = f"{base_url}/status"
    try:
        req = urllib.request.Request(status_url, method="GET")
        with urllib.request.urlopen(req, timeout=5):
            pass
    except (ConnectionRefusedError, urllib.error.URLError, OSError) as e:
        print(f"[voxtype] Error: cannot reach server at {base_url}", file=sys.stderr)
        print(f"[voxtype] ({e})", file=sys.stderr)
        _log_event(session_path, "server_unreachable", {"url": base_url, "error": str(e)})
        return 1

    # Save original terminal settings
    old_settings = None
    if sys.stdin.isatty():
        old_settings = termios.tcgetattr(sys.stdin.fileno())

    # Create pseudo-terminal
    master_fd, slave_fd = pty.openpty()

    # Set initial window size
    rows, cols = _get_winsize()
    sbar = StatusBar(agent_id) if status_bar else None
    _set_winsize(slave_fd, rows - (1 if sbar else 0), cols)

    stop_event = threading.Event()

    # Handle window resize
    def handle_sigwinch(signum, frame):
        rows, cols = _get_winsize()
        if sbar:
            sbar.on_resize(rows, cols)
        _set_winsize(master_fd, rows - (1 if sbar else 0), cols)

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

        # Clear terminal for clean start
        if clear_on_start:
            sys.stdout.buffer.write(b"\x1b[2J\x1b[H")
            sys.stdout.buffer.flush()

        # Init status bar before raw mode
        if sbar:
            sbar.init(rows, cols)

        # Put terminal in raw mode
        if old_settings:
            tty.setraw(sys.stdin.fileno())

        # Create thread-safe queue for serialized writes to PTY
        write_queue: queue.Queue = queue.Queue()

        # Create keystroke counter for session statistics
        keystroke_counter = KeystrokeCounter()

        # Start producer threads (read from stdin/SSE, put in queue)
        stdin_thread = threading.Thread(
            target=_read_from_stdin,
            args=(write_queue, stop_event, keystroke_counter),
            daemon=True,
        )
        # SSE-based IPC: connect to engine HTTP server
        sse_thread = threading.Thread(
            target=_read_from_sse,
            args=(agent_id, base_url, write_queue, stop_event, session_path, keystroke_counter, verbose),
            kwargs={"on_status": sbar.update if sbar else None},
            daemon=True,
        )
        # Start consumer thread (read from queue, write to PTY)
        writer_thread = threading.Thread(
            target=_write_to_pty,
            args=(master_fd, write_queue, stop_event, session_path, keystroke_counter, verbose),
            daemon=True,
        )

        stdin_thread.start()
        sse_thread.start()
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
                            if sbar:
                                sbar.after_child_output()
                        else:
                            break
                    except OSError:
                        break

                # Deferred status bar redraw after child settles from resize
                if sbar:
                    sbar.check_redraw()
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
        # Reset scroll region before restoring terminal
        if sbar:
            sbar.cleanup()

        # Restore terminal settings
        if old_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

        signal.signal(signal.SIGWINCH, old_sigwinch)

        try:
            os.close(master_fd)
        except OSError:
            pass
