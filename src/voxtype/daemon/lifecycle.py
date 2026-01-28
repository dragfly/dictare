"""Daemon lifecycle management - PID file, start, stop, status."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def get_data_dir() -> Path:
    """Get the voxtype data directory."""
    data_dir = Path.home() / ".local" / "share" / "voxtype"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_pid_path() -> Path:
    """Get path to daemon PID file."""
    return get_data_dir() / "daemon.pid"


def get_log_path() -> Path:
    """Get path to daemon log file."""
    return get_data_dir() / "daemon.log"


def get_socket_path() -> Path:
    """Get path to daemon Unix socket."""
    return Path("/tmp/voxtype-daemon.sock")


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
class DaemonStatus:
    """Daemon status information."""

    running: bool
    pid: int | None = None
    socket_exists: bool = False
    uptime_seconds: float | None = None


def get_daemon_status() -> DaemonStatus:
    """Get current daemon status."""
    pid = read_pid()
    socket_path = get_socket_path()
    socket_exists = socket_path.exists()

    if pid is None:
        return DaemonStatus(running=False, socket_exists=socket_exists)

    if not is_process_running(pid):
        # Stale PID file
        remove_pid()
        return DaemonStatus(running=False, socket_exists=socket_exists)

    # Process is running, try to get uptime from /proc (Linux) or ps (macOS)
    uptime = None
    try:
        if sys.platform == "linux":
            stat_path = Path(f"/proc/{pid}/stat")
            if stat_path.exists():
                # Get process start time from stat file
                stat = stat_path.read_text().split()
                start_time = int(stat[21]) / os.sysconf("SC_CLK_TCK")
                with open("/proc/uptime") as f:
                    system_uptime = float(f.read().split()[0])
                uptime = system_uptime - start_time
        else:
            # macOS: use ps
            result = subprocess.run(
                ["ps", "-o", "etime=", "-p", str(pid)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                etime = result.stdout.strip()
                uptime = _parse_etime(etime)
    except Exception:
        pass

    return DaemonStatus(
        running=True,
        pid=pid,
        socket_exists=socket_exists,
        uptime_seconds=uptime,
    )


def _parse_etime(etime: str) -> float:
    """Parse ps etime format (DD-HH:MM:SS or HH:MM:SS or MM:SS) to seconds."""
    str_parts = etime.replace("-", ":").split(":")
    parts = [int(p) for p in str_parts]

    if len(parts) == 4:
        # DD-HH:MM:SS
        return float(parts[0] * 86400 + parts[1] * 3600 + parts[2] * 60 + parts[3])
    elif len(parts) == 3:
        # HH:MM:SS
        return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    elif len(parts) == 2:
        # MM:SS
        return float(parts[0] * 60 + parts[1])
    else:
        return 0.0


def start_daemon(foreground: bool = False) -> int:
    """Start the daemon.

    Args:
        foreground: If True, run in foreground (blocking). Otherwise daemonize.

    Returns:
        0 on success, 1 on error.
    """
    status = get_daemon_status()
    if status.running:
        return 1  # Already running

    if foreground:
        # Run server directly in foreground
        from voxtype.daemon.server import DaemonServer

        server = DaemonServer()
        try:
            server.run()
        except KeyboardInterrupt:
            pass
        return 0
    else:
        # Daemonize: spawn subprocess
        log_path = get_log_path()

        # Use the current Python interpreter
        python = sys.executable
        cmd = [python, "-m", "voxtype.daemon.server"]

        # Open log file for output
        with open(log_path, "a") as log_file:
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
            )

        # Wait a moment for it to start
        time.sleep(0.5)

        # Check if it started successfully
        if process.poll() is not None:
            # Process exited
            return 1

        # Write PID
        write_pid(process.pid)
        return 0


def stop_daemon() -> int:
    """Stop the daemon.

    Returns:
        0 on success, 1 if not running.
    """
    status = get_daemon_status()
    if not status.running or status.pid is None:
        return 1

    try:
        os.kill(status.pid, signal.SIGTERM)

        # Wait for process to exit
        for _ in range(30):  # 3 seconds
            if not is_process_running(status.pid):
                break
            time.sleep(0.1)

        # Force kill if still running
        if is_process_running(status.pid):
            os.kill(status.pid, signal.SIGKILL)
            time.sleep(0.1)

    except OSError:
        pass

    # Cleanup
    remove_pid()
    socket_path = get_socket_path()
    if socket_path.exists():
        try:
            socket_path.unlink()
        except OSError:
            pass

    return 0
