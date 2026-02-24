"""macOS LaunchAgent management for dictare."""

from __future__ import annotations

import logging
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

LABEL = "com.dragfly.dictare"
TRAY_LABEL = "com.dragfly.dictare.tray"
LOG_DIR = Path.home() / "Library" / "Logs" / "dictare"

def get_plist_path() -> Path:
    """Return the LaunchAgent plist path."""
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"

def generate_plist(python_path: str) -> str:
    """Generate the LaunchAgent plist XML for the given python executable.

    If a .app bundle exists, ProgramArguments points to its executable
    so macOS associates permissions with the bundle (shows "Dictare" in
    system dialogs, and the bundle's CGEventTap can capture global hotkeys).
    Otherwise falls back to the raw python path.
    """
    from dictare.daemon.app_bundle import get_app_path, get_executable_path

    app_path = get_app_path()
    if app_path.exists():
        program_args = [get_executable_path()]
    else:
        program_args = [python_path, "-m", "dictare", "serve"]

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    plist: dict = {
        "Label": LABEL,
        "ProgramArguments": program_args,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_DIR / "stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "stderr.log"),
    }
    return plistlib.dumps(plist).decode()

def install() -> None:
    """Create .app bundle, write plist, and load the LaunchAgent.

    The .app bundle contains a Swift launcher that:
    1. Requests Microphone permission (shows "Dictare" in dialog)
    2. Captures global hotkey via CGEventTap (needs Accessibility + Input Monitoring)
    3. Spawns the Python engine and sends SIGUSR1 on hotkey tap

    Also installs and starts the tray LaunchAgent.
    """
    from dictare.daemon.app_bundle import create_app_bundle

    create_app_bundle(sys.executable)

    # Request Input Monitoring permission (shows system dialog on first install).
    # Must run BEFORE launchctl load — the dialog only works from terminal context.
    _request_input_monitoring()

    plist_path = get_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(generate_plist(sys.executable))

    # Stop existing service and verify it's dead before loading the new one.
    if is_loaded():
        _stop_service()
    # Kill orphan processes that survived a previous stop (e.g., old launcher
    # without proper SIGTERM handling).  This runs ALWAYS — is_loaded() may
    # return False even though the old process is still alive.
    _kill_orphan_processes()
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)

    # Also install tray auto-start
    if not is_tray_installed():
        install_tray()

def uninstall() -> None:
    """Unload and remove all LaunchAgents, then remove .app bundle."""
    from dictare.daemon.app_bundle import remove_app_bundle

    # Uninstall tray first
    uninstall_tray()

    plist_path = get_plist_path()
    if plist_path.exists():
        if is_loaded():
            _stop_service()
        plist_path.unlink(missing_ok=True)
    remove_app_bundle()

def is_installed() -> bool:
    """Check whether the plist file exists."""
    return get_plist_path().exists()

def is_loaded() -> bool:
    """Check whether the LaunchAgent is currently loaded in launchd."""
    result = subprocess.run(
        ["launchctl", "list", LABEL],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0

def start() -> None:
    """Load the LaunchAgent (starts the process and enables KeepAlive)."""
    plist_path = get_plist_path()
    if not plist_path.exists():
        raise RuntimeError("Service not installed. Run 'dictare service install' first.")
    if is_loaded():
        return  # Already loaded
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)

def stop() -> None:
    """Unload the LaunchAgent (stops the process and disables KeepAlive)."""
    if not is_loaded():
        return  # Already unloaded
    _stop_service()

def _get_service_pid() -> int | None:
    """Get the PID of the running service from launchctl."""
    result = subprocess.run(
        ["launchctl", "list", LABEL],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    # launchctl list <label> output: "PID" = 12345;
    for line in result.stdout.splitlines():
        if '"PID"' in line:
            try:
                pid_str = line.split("=")[1].strip().rstrip(";").strip()
                return int(pid_str)
            except (IndexError, ValueError):
                pass
    return None

def _wait_for_process_exit(pid: int, timeout: float = 3.0) -> bool:
    """Wait for a process to exit. Returns True if it exited within timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)  # Check if alive (signal 0 = no-op)
        except ProcessLookupError:
            return True  # Process is gone
        except PermissionError:
            return True  # Can't signal it — treat as gone
        time.sleep(0.1)
    return False

def _stop_service() -> None:
    """Unload the LaunchAgent and verify the process actually dies.

    launchctl unload sends SIGTERM, but NSApplication-based processes may not
    exit immediately.  If the process survives, we escalate to SIGKILL.
    """
    plist_path = get_plist_path()
    pid = _get_service_pid()

    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)

    if pid is not None:
        if not _wait_for_process_exit(pid):
            logger.warning("Service PID %d survived unload — sending SIGKILL", pid)
            try:
                os.kill(pid, 9)  # SIGKILL
            except ProcessLookupError:
                pass  # Already gone

def _request_input_monitoring() -> None:
    """Request Input Monitoring permission for the global hotkey.

    Strategy:
    1. Launch Dictare.app via `open` (as a real macOS app, not a Terminal
       child).  This triggers CGRequestListenEventAccess() inside the app's
       own process context, which may show the macOS permission prompt.
    2. If the prompt doesn't appear (ad-hoc signed binary on Sequoia), fall
       back to opening System Settings with manual instructions.

    A marker file keyed by launcher hash prevents re-prompting on updates
    that don't change the binary.
    """
    from dictare.daemon.app_bundle import get_app_path

    app_path = get_app_path()
    macos_dir = app_path / "Contents" / "MacOS"
    if not macos_dir.exists():
        return

    # Read the current launcher hash (written by create_app_bundle)
    hash_file = macos_dir / "launcher_hash"
    current_hash = hash_file.read_text().strip() if hash_file.exists() else ""

    # Check if we already guided the user for this exact binary
    marker = Path.home() / ".dictare" / "input_monitoring_setup"
    if marker.exists() and marker.read_text().strip() == current_hash:
        logger.debug("Input Monitoring setup already done for this binary")
        return

    # Attempt 1: Launch the .app with --request-input-monitoring via `open`.
    # Using `open` makes macOS treat it as a real app (own TCC identity),
    # not a child of Terminal (which would inherit Terminal's permissions).
    # --wait-apps blocks until the process exits, --args passes our flag.
    subprocess.run(
        ["open", "--wait-apps", str(app_path), "--args", "--request-input-monitoring"],
        capture_output=True, text=True, timeout=30,
    )

    # If the app reported success AND we trust it was actually prompted,
    # we're done.  But on Sequoia the API lies (returns true without prompt),
    # so we always show the fallback instructions on first install.
    print(
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  Input Monitoring permission required for global hotkey (Right Cmd)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "  If macOS prompted you — great, you're done.\n"
        "  If not, System Settings is opening to Input Monitoring.\n"
        f"  Click  +  →  select  {app_path}\n"
        "  Then toggle it ON.\n"
        "\n"
        "  (Only needed once — survives updates and restarts.)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    subprocess.run(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"],
        check=False,
    )

    # Write marker so next install with same binary skips
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(current_hash)

def _kill_orphan_processes() -> None:
    """Kill orphaned Dictare processes that survived a previous launchctl unload.

    When upgrading from a version with broken SIGTERM handling (pre-b191),
    the old launcher + engine may still be alive even after launchctl unload.
    This function kills them by PID file and by binary path pattern.
    """
    # 1. Kill engine via PID file
    pid_file = Path.home() / ".dictare" / "engine.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Check alive
            logger.warning("Orphaned engine PID %d — killing", pid)
            os.kill(pid, 9)  # SIGKILL
            pid_file.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    # 2. Kill Dictare.app launcher by binary path
    subprocess.run(
        ["pkill", "-9", "-f", "Dictare.app/Contents/MacOS/Dictare"],
        capture_output=True,
    )

    # 3. Clean stale hotkey_status so the new launcher starts fresh
    hotkey_file = Path.home() / ".dictare" / "hotkey_status"
    hotkey_file.unlink(missing_ok=True)

# --------------------------------------------------------------------------
# Tray LaunchAgent
# --------------------------------------------------------------------------

def get_tray_plist_path() -> Path:
    """Return the tray LaunchAgent plist path."""
    return Path.home() / "Library" / "LaunchAgents" / f"{TRAY_LABEL}.plist"

def install_tray() -> None:
    """Create and load a LaunchAgent for the tray app (auto-start at login)."""
    import sys

    python_path = sys.executable
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    plist: dict = {
        "Label": TRAY_LABEL,
        "ProgramArguments": [python_path, "-m", "dictare", "tray", "start", "--foreground"],
        "RunAtLoad": True,
        "KeepAlive": False,  # don't restart if user quits tray
        "StandardOutPath": str(LOG_DIR / "tray-stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "tray-stderr.log"),
    }

    plist_path = get_tray_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plistlib.dumps(plist).decode())
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)

def uninstall_tray() -> None:
    """Unload and remove the tray LaunchAgent."""
    plist_path = get_tray_plist_path()
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink(missing_ok=True)

def is_tray_installed() -> bool:
    """Check whether the tray plist exists."""
    return get_tray_plist_path().exists()
