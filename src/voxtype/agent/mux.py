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
from datetime import datetime, timezone
from fcntl import ioctl
from pathlib import Path

from voxtype import __version__

# Default directory for agent files
DEFAULT_OUTPUT_DIR = "/tmp"

# Session logs directory
SESSIONS_DIR = Path.home() / ".local" / "share" / "voxtype" / "sessions"


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
    input_file: str,
) -> None:
    """Write session start metadata to log file."""
    metadata = {
        "event": "session_start",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "voxtype_version": __version__,
        "agent_id": agent_id,
        "command": command,
        "input_file": input_file,
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


def _write_session_end(session_path: Path, exit_code: int) -> None:
    """Write session end event to log file."""
    metadata = {
        "event": "session_end",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "exit_code": exit_code,
    }
    with open(session_path, "a") as f:
        f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        f.flush()


def get_agent_file(agent_id: str, output_dir: str | None = None) -> str:
    """Get the file path for an agent.

    Args:
        agent_id: Agent identifier (e.g., 'macinanumeri').
        output_dir: Directory for agent files (default: /tmp).

    Returns:
        Full path to agent file (e.g., /tmp/macinanumeri.voxtype).
    """
    base_dir = output_dir or DEFAULT_OUTPUT_DIR
    return f"{base_dir}/{agent_id}.voxtype"


def create_agent_file(agent_id: str, output_dir: str | None = None) -> str:
    """Create an empty agent file.

    Args:
        agent_id: Agent identifier.
        output_dir: Directory for agent files.

    Returns:
        Path to the created file.
    """
    filepath = get_agent_file(agent_id, output_dir)
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    # Create empty file (or truncate if exists)
    with open(filepath, "w") as f:
        pass

    return filepath


def _read_from_stdin(
    write_queue: queue.Queue, stop_event: threading.Event
) -> None:
    """Read from keyboard in raw mode and put data in queue."""
    try:
        while not stop_event.is_set():
            r, _, _ = select.select([sys.stdin.fileno()], [], [], 0.1)
            if sys.stdin.fileno() in r:
                data = os.read(sys.stdin.fileno(), 1024)
                if not data:
                    break
                # Put raw bytes directly in queue
                write_queue.put(("raw", data))
    except (BrokenPipeError, IOError, OSError):
        pass


def _read_from_file(
    filepath: str, write_queue: queue.Queue, stop_event: threading.Event
) -> None:
    """Monitor file and put parsed messages in queue.

    JSONL Protocol from voxtype:
    - {"text": "hello"}                 -> type "hello"
    - {"text": "hello\\n"}              -> type "hello" + Alt+Enter (visual newline)
    - {"text": "hello", "submit": true} -> type "hello" + Enter
    - {"submit": true}                  -> just Enter

    Uses simple Python readline() which works reliably for append-only files.
    """
    try:
        with open(filepath, "r") as f:
            # Seek to end of file (tail -f style)
            f.seek(0, os.SEEK_END)

            while not stop_event.is_set():
                line = f.readline()
                if line:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Put parsed message in queue for processing
                    write_queue.put(("msg", msg))
                else:
                    # No new data - small sleep then retry
                    time.sleep(0.05)
    except (BrokenPipeError, IOError, OSError):
        pass


def _write_to_pty(
    master_fd: int, write_queue: queue.Queue, stop_event: threading.Event
) -> None:
    """Consume from queue and write to PTY.

    This is the ONLY thread that writes to master_fd, ensuring serialization.
    """
    # Alt+Enter for visual newline (ESC + CR)
    ALT_ENTER = b"\x1b\r"
    ENTER = b"\r"

    while not stop_event.is_set():
        try:
            # Block with timeout so we can check stop_event
            item = write_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        msg_type, data = item

        try:
            if msg_type == "raw":
                # Raw bytes from stdin - write directly
                os.write(master_fd, data)
            elif msg_type == "msg":
                # Parsed JSONL message from file
                text = data.get("text", "")
                if text:
                    has_visual_newline = text.endswith("\n")
                    if has_visual_newline:
                        text = text.rstrip("\n")

                    if text:
                        os.write(master_fd, text.encode())
                        time.sleep(0.005)

                    # Send Alt+Enter for visual newline
                    if has_visual_newline:
                        os.write(master_fd, ALT_ENTER)
                        time.sleep(0.005)

                # Handle submit flag
                if data.get("submit"):
                    time.sleep(0.01)
                    os.write(master_fd, ENTER)
        except (BrokenPipeError, IOError, OSError):
            break


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    """Set terminal window size."""
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        ioctl(fd, termios.TIOCSWINSZ, winsize)
    except (OSError, IOError):
        pass


def _get_winsize() -> tuple[int, int]:
    """Get current terminal window size."""
    try:
        winsize = struct.pack("HHHH", 0, 0, 0, 0)
        result = ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, winsize)
        rows, cols, _, _ = struct.unpack("HHHH", result)
        return rows, cols
    except (OSError, IOError):
        return 24, 80


def run_agent(
    agent_id: str,
    command: list[str],
    output_dir: str | None = None,
    quiet: bool = False,
) -> int:
    """Run a command with multiplexed input from stdin and voxtype.

    Args:
        agent_id: Agent identifier (e.g., 'macinanumeri').
        command: Command and arguments to run.
        output_dir: Directory for agent files (default: /tmp).
        quiet: Suppress info messages.

    Returns:
        Exit code of the process.
    """
    # Create the agent file
    input_file = create_agent_file(agent_id, output_dir)

    # Create session log
    session_path = _get_session_log_path(agent_id)
    _write_session_start(session_path, agent_id, command, input_file)

    if not quiet:
        print(f"[voxtype {__version__}] Agent: {agent_id}", file=sys.stderr)
        print(f"[voxtype {__version__}] File: {input_file}", file=sys.stderr)
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
        # This prevents race conditions between stdin and file input
        write_queue: queue.Queue = queue.Queue()

        # Start producer threads (read from stdin/file, put in queue)
        stdin_thread = threading.Thread(
            target=_read_from_stdin,
            args=(write_queue, stop_event),
            daemon=True,
        )
        file_thread = threading.Thread(
            target=_read_from_file,
            args=(input_file, write_queue, stop_event),
            daemon=True,
        )
        # Start consumer thread (read from queue, write to PTY)
        writer_thread = threading.Thread(
            target=_write_to_pty,
            args=(master_fd, write_queue, stop_event),
            daemon=True,
        )

        stdin_thread.start()
        file_thread.start()
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

        # Log session end
        _write_session_end(session_path, exit_code)
        return exit_code

    finally:
        # Restore terminal settings
        if old_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

        signal.signal(signal.SIGWINCH, old_sigwinch)

        try:
            os.close(master_fd)
        except OSError:
            pass
