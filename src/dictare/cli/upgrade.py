"""Upgrade and rollback Dictare runtimes."""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Annotated

import typer

from dictare.cli._helpers import console


def _get_backend():
    if sys.platform == "darwin":
        from dictare.daemon import launchd

        return launchd
    if sys.platform == "linux":
        from dictare.daemon import systemd

        return systemd
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def _latest_pypi_version() -> str:
    with urllib.request.urlopen("https://pypi.org/pypi/dictare/json", timeout=15) as response:
        data = json.load(response)
    return str(data["info"]["version"])


def _version_from_path(path: str) -> str | None:
    name = Path(path).name
    match = re.search(r"dictare-([0-9][A-Za-z0-9.+!_-]*)\.(?:tar\.gz|whl|zip)$", name)
    return match.group(1) if match else None


def _parse_extras(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def register(app: typer.Typer) -> None:
    """Register top-level upgrade and rollback commands."""

    @app.command("upgrade")
    def upgrade(
        version: Annotated[
            str | None,
            typer.Option("--version", help="Install a specific Dictare version."),
        ] = None,
        from_path: Annotated[
            str | None,
            typer.Option("--from-path", help="Install from a local sdist/wheel/path."),
        ] = None,
        extras: Annotated[
            str | None,
            typer.Option("--extras", help="Comma-separated extras override."),
        ] = None,
        reinstall: Annotated[
            bool,
            typer.Option("--reinstall", help="Reinstall into an existing version directory."),
        ] = False,
        no_restart: Annotated[
            bool,
            typer.Option("--no-restart", help="Leave services stopped after activation."),
        ] = False,
    ) -> None:
        """Install a new runtime, activate it atomically, and repair services."""
        from dictare.cli.repair import repair_runtime
        from dictare.runtime_store import (
            activate_runtime,
            current_runtime,
            install_runtime,
            snapshot,
        )

        target_version = version or (_version_from_path(from_path) if from_path else None)
        if target_version is None:
            try:
                target_version = _latest_pypi_version()
            except Exception as e:
                console.print(f"[red]Could not resolve latest version:[/] {e}")
                raise typer.Exit(1)

        before = snapshot()
        if before.current_version == target_version and not reinstall:
            console.print(f"[green]Dictare {target_version} is already active[/]")
            return

        console.print(f"[dim]Installing Dictare runtime {target_version}...[/]")
        try:
            runtime = install_runtime(
                target_version,
                source=from_path,
                extras=_parse_extras(extras),
                reinstall=reinstall,
            )
        except Exception as e:
            console.print(f"[red]Runtime install failed:[/] {e}")
            raise typer.Exit(1)

        backend = _get_backend()
        was_installed = backend.is_installed()
        was_running = backend.is_loaded() if was_installed and hasattr(backend, "is_loaded") else False

        try:
            if was_running:
                console.print("[dim]Stopping Dictare services...[/]")
                backend.stop()

            activate_runtime(runtime)
            repair_runtime(no_start=no_restart or not was_running)

            current = current_runtime()
            console.print(f"[green]Dictare runtime active:[/] {current.name if current else target_version}")
            if before.current_version:
                console.print(f"[dim]Previous runtime:[/] {before.current_version}")
        except Exception as e:
            console.print(f"[red]Upgrade activation failed:[/] {e}")
            raise typer.Exit(1)

    @app.command("rollback")
    def rollback(
        no_restart: Annotated[
            bool,
            typer.Option("--no-restart", help="Leave services stopped after rollback."),
        ] = False,
    ) -> None:
        """Rollback to the previous Dictare runtime."""
        from dictare.cli.repair import repair_runtime
        from dictare.runtime_store import rollback_runtime

        backend = _get_backend()
        was_installed = backend.is_installed()
        was_running = backend.is_loaded() if was_installed and hasattr(backend, "is_loaded") else False

        try:
            if was_running:
                backend.stop()
            runtime = rollback_runtime()
            repair_runtime(no_start=no_restart or not was_running)
        except Exception as e:
            console.print(f"[red]Rollback failed:[/] {e}")
            raise typer.Exit(1)

        console.print(f"[green]Rolled back to Dictare runtime:[/] {runtime.name}")
