"""Linux systemd user service management for dictare."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

UNIT_NAME = "dictare.service"

def get_unit_path() -> Path:
    """Return the systemd user unit path."""
    return Path.home() / ".config" / "systemd" / "user" / UNIT_NAME

def _gi_typelib_path() -> str:
    """Return GI_TYPELIB_PATH for the current architecture."""
    import platform

    arch = platform.machine()
    arch_map = {
        "aarch64": "aarch64-linux-gnu",
        "arm64": "aarch64-linux-gnu",
        "armv7l": "arm-linux-gnueabihf",
        "riscv64": "riscv64-linux-gnu",
    }
    triplet = arch_map.get(arch, "x86_64-linux-gnu")
    return f"/usr/lib/girepository-1.0:/usr/lib/{triplet}/girepository-1.0"

def generate_unit(python_path: str) -> str:
    """Generate the systemd unit file content."""
    gi_path = _gi_typelib_path()
    return textwrap.dedent(f"""\
        [Unit]
        Description=Dictare voice engine
        After=network.target
        StartLimitIntervalSec=60
        StartLimitBurst=5

        [Service]
        Type=simple
        ExecStart={python_path} -m dictare serve
        Restart=always
        RestartSec=5
        Environment=PYTHONUNBUFFERED=1
        Environment=GI_TYPELIB_PATH={gi_path}

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

def is_loaded() -> bool:
    """Check whether the service is currently active."""
    result = subprocess.run(
        ["systemctl", "--user", "is-active", UNIT_NAME],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == "active"

def start() -> None:
    """Start the service."""
    subprocess.run(["systemctl", "--user", "start", UNIT_NAME], check=True)

def stop() -> None:
    """Stop the service."""
    subprocess.run(["systemctl", "--user", "stop", UNIT_NAME], check=True)
