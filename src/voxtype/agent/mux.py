"""Agent multiplexer - run commands with merged stdin and voxtype input."""

from __future__ import annotations

import json
import os
import pty
import select
import signal
import struct
import sys
import termios
import threading
import time
import tty
from fcntl import ioctl
from pathlib import Path

# Default directory for agent files
DEFAULT_OUTPUT_DIR = "/tmp"

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

def _read_from_stdin(master_fd: int, stop_event: threading.Event) -> None:
    """Read from keyboard in raw mode and send to process via PTY."""
    try:
        while not stop_event.is_set():
            r, _, _ = select.select([sys.stdin.fileno()], [], [], 0.1)
            if sys.stdin.fileno() in r:
                data = os.read(sys.stdin.fileno(), 1024)
                if not data:
                    break
                os.write(master_fd, data)
    except (BrokenPipeError, IOError, OSError):
        pass

def _read_from_file(filepath: str, master_fd: int, stop_event: threading.Event) -> None:
    """Monitor file and send new data to process via PTY.

    JSONL Protocol from voxtype:
    - {"text": "hello"}                 -> type "hello"
    - {"text": "hello\\n"}              -> type "hello" + Shift+Enter (visual newline)
    - {"text": "hello", "submit": true} -> type "hello" + Enter
    - {"submit": true}                  -> just Enter
    """
    # Shift+Enter for visual newline (works in most apps)
    SHIFT_ENTER = b"\x1b[13;2u"  # CSI sequence for Shift+Enter
    # Fallback: Alt+Enter (ESC + CR)
    ALT_ENTER = b"\x1b\r"
    ENTER = b"\r"

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

                    # Handle text field
                    text = msg.get("text", "")
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
                    if msg.get("submit"):
                        time.sleep(0.01)
                        os.write(master_fd, ENTER)
                else:
                    time.sleep(0.1)
    except (BrokenPipeError, IOError, OSError):
        pass

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

    if not quiet:
        print(f"[voxtype] Agent: {agent_id}", file=sys.stderr)
        print(f"[voxtype] File: {input_file}", file=sys.stderr)
        print(f"[voxtype] Running: {' '.join(command)}", file=sys.stderr)

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

        # Start input threads
        stdin_thread = threading.Thread(
            target=_read_from_stdin,
            args=(master_fd, stop_event),
            daemon=True,
        )
        file_thread = threading.Thread(
            target=_read_from_file,
            args=(input_file, master_fd, stop_event),
            daemon=True,
        )

        stdin_thread.start()
        file_thread.start()

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
            return os.WEXITSTATUS(status)
        return 1

    finally:
        # Restore terminal settings
        if old_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

        signal.signal(signal.SIGWINCH, old_sigwinch)

        try:
            os.close(master_fd)
        except OSError:
            pass
