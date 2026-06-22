"""Repair Dictare runtime and service integration."""

from __future__ import annotations

import sys
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


def repair_runtime(
    *,
    no_start: bool = False,
    force_bundle_migration: bool = False,
) -> None:
    """Repair runtime store, launcher path, and service definitions."""
    from dictare.runtime_store import (
        current_runtime,
        ensure_shim,
        write_launcher_python_path,
    )

    runtime = current_runtime()
    if runtime is not None:
        ensure_shim()
        write_launcher_python_path()

    if sys.platform == "darwin":
        try:
            from dictare.daemon.app_bundle import migrate_signed_bundle_from_cellar

            migrate_signed_bundle_from_cellar(force=force_bundle_migration)
        except Exception as e:
            console.print(f"[yellow]App bundle migration skipped:[/] {e}")

    backend = _get_backend()
    was_installed = backend.is_installed()
    was_running = backend.is_loaded() if hasattr(backend, "is_loaded") else False

    if was_running:
        backend.stop()

    backend.install()

    if sys.platform == "linux" and not no_start:
        backend.start()
    elif no_start:
        try:
            backend.stop()
        except Exception:
            pass
    elif was_installed and not was_running and sys.platform == "darwin":
        # launchd.install() loads the agent; preserve an intentionally stopped service.
        backend.stop()


def register(app: typer.Typer) -> None:
    """Register top-level repair command."""

    @app.command("repair")
    def repair(
        no_start: Annotated[
            bool,
            typer.Option("--no-start", help="Repair files but leave services stopped."),
        ] = False,
        force_bundle_migration: Annotated[
            bool,
            typer.Option(
                "--force-bundle-migration",
                help="Replace the macOS app bundle even when it looks valid.",
            ),
        ] = False,
    ) -> None:
        """Repair Dictare runtime, service files, and launcher integration."""
        try:
            repair_runtime(
                no_start=no_start,
                force_bundle_migration=force_bundle_migration,
            )
        except Exception as e:
            console.print(f"[red]Repair failed:[/] {e}")
            raise typer.Exit(1)

        console.print("[green]Dictare repair complete[/]")
