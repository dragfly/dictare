"""Linux systemd user service management for voxtype."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

UNIT_NAME = "voxtype.service"


def get_unit_path() -> Path:
    """Return the systemd user unit path."""
    return Path.home() / ".config" / "systemd" / "user" / UNIT_NAME


def generate_unit(python_path: str) -> str:
    """Generate the systemd unit file content."""
    return textwrap.dedent(f"""\
        [Unit]
        Description=Voxtype voice engine
        After=network.target

        [Service]
        Type=simple
        ExecStart={python_path} -m voxtype engine start -d --agents
        Restart=on-failure
        RestartSec=5

        [Install]
        WantedBy=default.target
    """)


def install() -> None:
    """Write unit file and enable the service."""
    import sys

    unit_path = get_unit_path()
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(generate_unit(sys.executable))
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", UNIT_NAME], check=True)


def uninstall() -> None:
    """Disable and remove the service."""
    unit_path = get_unit_path()
    if unit_path.exists():
        subprocess.run(["systemctl", "--user", "disable", UNIT_NAME], check=False)
        subprocess.run(["systemctl", "--user", "stop", UNIT_NAME], check=False)
        unit_path.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)


def is_installed() -> bool:
    """Check whether the unit file exists."""
    return get_unit_path().exists()


def start() -> None:
    """Start the service."""
    subprocess.run(["systemctl", "--user", "start", UNIT_NAME], check=True)


def stop() -> None:
    """Stop the service."""
    subprocess.run(["systemctl", "--user", "stop", UNIT_NAME], check=True)
