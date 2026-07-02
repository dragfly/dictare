"""Uninstall Dictare-owned runtime and service state."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from dictare.cli._helpers import console


def _trash_root() -> Path:
    return Path.home() / ".dictare" / "trash" / f"uninstall.{int(time.time())}"


def _move_path(path: Path, trash: Path) -> Path | None:
    """Move a path into Dictare trash and return the destination."""
    if not path.exists() and not path.is_symlink():
        return None
    trash.mkdir(parents=True, exist_ok=True)
    target = trash / path.name
    counter = 0
    while target.exists() or target.is_symlink():
        counter += 1
        target = trash / f"{path.name}.{counter}"
    shutil.move(str(path), str(target))
    return target


def _run_best_effort(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False, capture_output=True)


def _stop_and_move_services(trash: Path) -> None:
    if sys.platform == "darwin":
        launch_agents = Path.home() / "Library" / "LaunchAgents"
        paths = [
            launch_agents / "dev.dragfly.dictare.plist",
            launch_agents / "dev.dragfly.dictare.tray.plist",
        ]
        for plist in paths:
            _run_best_effort(["launchctl", "unload", str(plist)])
        _run_best_effort(["pkill", "-f", "Dictare.app/Contents/MacOS/Dictare"])
        _run_best_effort(["pkill", "-f", "dictare serve"])
        _run_best_effort(["pkill", "-f", "dictare.tray"])
        for plist in paths:
            _move_path(plist, trash)
        _move_path(Path.home() / "Applications" / "Dictare.app", trash)
        return

    if sys.platform == "linux":
        unit = Path.home() / ".config" / "systemd" / "user" / "dictare.service"
        _run_best_effort(["systemctl", "--user", "stop", "dictare.service"])
        _run_best_effort(["systemctl", "--user", "disable", "dictare.service"])
        _move_path(unit, trash)
        _run_best_effort(["systemctl", "--user", "daemon-reload"])


def uninstall_runtime(*, wipe_config: bool = False) -> Path:
    """Move Dictare-owned runtime/service state aside and return trash path."""
    from dictare.runtime_store import (
        BIN_DIR,
        CURRENT_LINK,
        LOCK_DIR,
        PREVIOUS_LINK,
        RUNTIME_ROOT,
        SHIM_PATH,
        VERSIONS_DIR,
    )

    trash = _trash_root()
    _stop_and_move_services(trash)

    for path in (
        SHIM_PATH,
        CURRENT_LINK,
        PREVIOUS_LINK,
        VERSIONS_DIR,
        LOCK_DIR,
        Path.home() / ".dictare" / "python_path",
        Path.home() / ".dictare" / "homebrew_bundle_path",
    ):
        moved = _move_path(path, trash)
        if moved:
            console.print(f"[dim]Moved {path} -> {moved}[/]")

    # Remove now-empty parent dirs only. Keep user data under runtime root.
    for path in (BIN_DIR, RUNTIME_ROOT):
        try:
            path.rmdir()
        except OSError:
            pass

    if wipe_config:
        for path in (
            Path.home() / ".config" / "dictare",
            Path.home() / ".local" / "share" / "dictare",
        ):
            moved = _move_path(path, trash)
            if moved:
                console.print(f"[dim]Moved {path} -> {moved}[/]")

    return trash


def register(app: typer.Typer) -> None:
    """Register top-level uninstall command."""

    @app.command("uninstall")
    def uninstall(
        wipe_config: Annotated[
            bool,
            typer.Option(
                "--wipe-config",
                help="Also move ~/.config/dictare and remaining ~/.local/share/dictare data aside.",
            ),
        ] = False,
    ) -> None:
        """Uninstall Dictare runtime/service state while preserving Homebrew entry point."""
        try:
            trash = uninstall_runtime(wipe_config=wipe_config)
        except Exception as e:
            console.print(f"[red]Uninstall failed:[/] {e}")
            raise typer.Exit(1)

        console.print("[green]Dictare runtime uninstalled[/]")
        console.print(f"[dim]Moved files are in {trash}[/]")
        console.print()
        console.print("[dim]If Dictare was installed with Homebrew, remove the entry point with:[/]")
        console.print("  brew uninstall dictare")
