"""macOS LaunchAgent management for voxtype."""

from __future__ import annotations

import glob
import plistlib
import subprocess
from pathlib import Path

LABEL = "com.dragfly.voxtype"
TRAY_LABEL = "com.dragfly.voxtype.tray"
LOG_DIR = Path.home() / "Library" / "Logs" / "voxtype"


def get_plist_path() -> Path:
    """Return the LaunchAgent plist path."""
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def generate_plist(python_path: str, pythonpath: str | None = None) -> str:
    """Generate the LaunchAgent plist XML for the given python executable.

    If a .app bundle exists, ProgramArguments points to its executable
    so macOS associates permissions with the bundle (shows in Accessibility).
    Otherwise falls back to the raw python path.

    Args:
        python_path: Path to the Python interpreter.
        pythonpath: Optional PYTHONPATH to inject (used when the service Python
            differs from the venv Python — e.g. brew Python.app + uv venv packages).
    """
    from voxtype.daemon.app_bundle import get_app_path, get_executable_path

    app_path = get_app_path()
    if app_path.exists():
        program_args = [get_executable_path()]
    else:
        program_args = [python_path, "-m", "voxtype", "serve"]

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    plist: dict = {
        "Label": LABEL,
        "ProgramArguments": program_args,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_DIR / "stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "stderr.log"),
    }
    if pythonpath:
        plist["EnvironmentVariables"] = {"PYTHONPATH": pythonpath}
    return plistlib.dumps(plist).decode()


def _find_brew_python_app() -> str | None:
    """Find the brew-installed Python.app binary (already trusted in macOS TCC).

    Brew Python is a proper .app bundle. On most macOS setups it has already
    been granted Accessibility permission (shown as "Python" in System Settings).
    We prefer it over uv-managed Python (a standalone binary with no .app bundle
    and no TCC entry) so that pynput's CGEventTap works from the launchd service.
    """
    for prefix in ("/opt/homebrew", "/usr/local"):
        pattern = (
            f"{prefix}/Cellar/python@3.11/*/Frameworks/Python.framework"
            f"/Versions/3.11/Resources/Python.app/Contents/MacOS/Python"
        )
        matches = sorted(glob.glob(pattern), reverse=True)
        if matches:
            return matches[0]
    return None


def _is_ax_trusted(python_exe: str) -> bool:
    """Return True if the given Python binary has Accessibility TCC trust.

    Spawns the binary in a subprocess and calls AXIsProcessTrusted() from
    inside it, which checks whether *that* binary is in the TCC database.
    """
    try:
        result = subprocess.run(
            [
                python_exe, "-c",
                "import ctypes; lib=ctypes.cdll.LoadLibrary("
                "'/System/Library/Frameworks/ApplicationServices.framework"
                "/ApplicationServices');"
                "lib.AXIsProcessTrusted.restype=ctypes.c_bool;"
                "print(bool(lib.AXIsProcessTrusted()))",
            ],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() == "True"
    except Exception:
        return False


def install() -> None:
    """Create .app bundle, write plist, and load the LaunchAgent.

    On macOS, if the current Python is not trusted in TCC Accessibility
    (e.g. a uv-managed standalone binary), we automatically switch to the
    brew Python.app (which ships as a proper .app bundle and is already
    trusted on most systems). The venv site-packages are injected via
    PYTHONPATH so all installed packages remain accessible.

    Also installs and starts the tray LaunchAgent.
    """
    import sys

    from voxtype.daemon.app_bundle import create_app_bundle

    bundle_python = sys.executable
    pythonpath: str | None = None

    if sys.platform == "darwin" and not _is_ax_trusted(sys.executable):
        brew = _find_brew_python_app()
        if brew and _is_ax_trusted(brew):
            try:
                r = subprocess.run(
                    [sys.executable, "-c",
                     "import site; print(site.getsitepackages()[0])"],
                    capture_output=True, text=True, timeout=5,
                )
                venv_site = r.stdout.strip() if r.returncode == 0 else None
            except Exception:
                venv_site = None
            if venv_site:
                bundle_python = brew
                pythonpath = venv_site

    create_app_bundle(bundle_python)
    plist_path = get_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(generate_plist(bundle_python, pythonpath=pythonpath))

    # Unload first if already running so the updated plist takes effect.
    if is_loaded():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)

    # Also install tray auto-start
    if not is_tray_installed():
        install_tray()


def uninstall() -> None:
    """Unload and remove all LaunchAgents, then remove .app bundle."""
    from voxtype.daemon.app_bundle import remove_app_bundle

    # Uninstall tray first
    uninstall_tray()

    plist_path = get_plist_path()
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
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
        raise RuntimeError("Service not installed. Run 'voxtype service install' first.")
    if is_loaded():
        return  # Already loaded
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)


def stop() -> None:
    """Unload the LaunchAgent (stops the process and disables KeepAlive)."""
    plist_path = get_plist_path()
    if not is_loaded():
        return  # Already unloaded
    subprocess.run(["launchctl", "unload", str(plist_path)], check=True)


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
        "ProgramArguments": [python_path, "-m", "voxtype", "tray", "start", "--foreground"],
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
