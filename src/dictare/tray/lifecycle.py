"""Tray lifecycle management - PID file, start, stop, status."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def get_data_dir() -> Path:
    """Get the dictare data directory."""
    data_dir = Path.home() / ".local" / "share" / "dictare"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_pid_path() -> Path:
    """Get path to tray PID file."""
    return get_data_dir() / "tray.pid"


def write_pid(pid: int) -> None:
    """Write PID to file."""
    get_pid_path().write_text(str(pid))


def read_pid() -> int | None:
    """Read PID from file, return None if not found or invalid."""
    pid_path = get_pid_path()
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text().strip())
    except (ValueError, OSError):
        return None


def remove_pid() -> None:
    """Remove PID file."""
    pid_path = get_pid_path()
    if pid_path.exists():
        pid_path.unlink()


def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@dataclass
class TrayStatus:
    """Tray status information."""

    running: bool
    pid: int | None = None


def get_tray_status() -> TrayStatus:
    """Get current tray status."""
    pid = read_pid()

    if pid is None:
        return TrayStatus(running=False)

    if not is_process_running(pid):
        # Stale PID file
        remove_pid()
        return TrayStatus(running=False)

    return TrayStatus(running=True, pid=pid)


def start_tray(foreground: bool = False) -> int:
    """Start the tray application.

    Args:
        foreground: If True, run in foreground (blocking). If False, daemonize.

    Returns:
        0 on success, 1 on failure.
    """
    # Check if already running
    status = get_tray_status()
    if status.running:
        return 1  # Already running

    if foreground:
        # Run directly in foreground
        from dictare.tray.app import TrayApp

        # Write our own PID
        write_pid(os.getpid())

        try:
            app = TrayApp()
            app.run()
        finally:
            remove_pid()

        return 0

    else:
        # Daemonize: spawn subprocess
        python = sys.executable
        cmd = [python, "-m", "dictare.tray.app"]

        # Start detached process
        if sys.platform == "darwin":
            # macOS: use start_new_session
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            # Linux: use nohup-like behavior
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        # Wait a moment for it to start
        time.sleep(0.5)

        # Check if it started successfully
        if process.poll() is not None:
            # Process exited immediately
            return 1

        # Write PID
        write_pid(process.pid)
        return 0


def stop_tray() -> int:
    """Stop the tray application.

    Returns:
        0 on success, 1 if not running.
    """
    status = get_tray_status()
    if not status.running or status.pid is None:
        return 1

    try:
        # Send SIGINT for graceful shutdown (like Ctrl+C)
        os.kill(status.pid, signal.SIGINT)

        # Wait for process to exit
        for _ in range(30):  # 3 seconds
            if not is_process_running(status.pid):
                break
            time.sleep(0.1)

        # Force kill if still running
        if is_process_running(status.pid):
            os.kill(status.pid, signal.SIGTERM)
            time.sleep(0.5)

        if is_process_running(status.pid):
            os.kill(status.pid, signal.SIGKILL)
            time.sleep(0.1)

    except OSError:
        pass

    # Cleanup
    remove_pid()
    return 0
