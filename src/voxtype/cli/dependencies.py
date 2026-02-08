"""System dependency management commands."""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.table import Table

from voxtype.cli._helpers import console

app = typer.Typer(help="Manage system dependencies.", no_args_is_help=True)

def _check_dependencies_internal() -> tuple[list, bool, list, list]:
    """Check dependencies and return results.

    Returns:
        Tuple of (results, all_ok, missing_with_hints, optional_with_hints)
    """
    from voxtype.utils.platform import check_dependencies

    results = check_dependencies()

    all_ok = True
    missing_with_hints = []
    optional_with_hints = []

    for result in results:
        if result.available:
            pass  # OK
        elif result.required:
            all_ok = False
            if result.install_hint:
                missing_with_hints.append(result)
        else:
            if result.install_hint:
                optional_with_hints.append(result)

    return results, all_ok, missing_with_hints, optional_with_hints

def _display_dependencies(results, all_ok: bool, missing_with_hints: list, optional_with_hints: list) -> None:
    """Display dependency check results."""
    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    for result in results:
        if result.available:
            status = "[green]OK[/]"
        elif result.required:
            status = "[red]MISSING[/]"
        else:
            status = "[yellow]OPTIONAL[/]"

        table.add_row(result.name, status, result.message)

    console.print(table)
    console.print()

    if all_ok:
        console.print("[green]All required dependencies are available![/]")
        # Show GPU acceleration hint if applicable
        gpu_hints = [r for r in optional_with_hints if r.name in ("NVIDIA GPU", "Apple Silicon")]
        if gpu_hints:
            console.print("\n[bold]To enable hardware acceleration:[/]")
            for result in gpu_hints:
                hint = result.install_hint.replace("[", r"\[")  # type: ignore
                console.print(f"  [cyan]{hint}[/]")
    else:
        console.print("[red]Some required dependencies are missing.[/]")
        if missing_with_hints:
            console.print("\n[bold]To fix, run:[/]")
            # Deduplicate hints
            seen_hints: set[str] = set()
            for result in missing_with_hints:
                if result.install_hint and result.install_hint not in seen_hints:
                    seen_hints.add(result.install_hint)
                    hint = result.install_hint.replace("[", r"\[")
                    console.print(f"  [cyan]{hint}[/]")
        console.print("\n[dim]Or run: voxtype dependencies resolve[/]")

    # Check for text injection method (Linux only)
    if sys.platform == "linux":
        has_ydotool = any(r.available for r in results if r.name == "ydotool")
        if not has_ydotool:
            console.print(
                "\n[red]Warning:[/] ydotool not available. "
                "Install ydotool and start ydotoold daemon."
            )

@app.command("check")
def deps_check() -> None:
    """Check system dependencies.

    Shows status of all required and optional dependencies.
    """
    console.print("[dim]Checking dependencies...[/]")

    results, all_ok, missing_with_hints, optional_with_hints = _check_dependencies_internal()
    _display_dependencies(results, all_ok, missing_with_hints, optional_with_hints)

    if not all_ok:
        raise typer.Exit(1)

@app.command("resolve")
def deps_resolve(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be installed without installing"),
    ] = False,
) -> None:
    """Automatically resolve missing dependencies.

    Attempts to install missing dependencies using system package managers
    (brew on macOS, apt on Linux) and pip.

    Examples:
        voxtype dependencies resolve           # Install missing deps
        voxtype dependencies resolve --dry-run # Show what would be installed
    """
    import subprocess

    console.print("[dim]Checking dependencies...[/]")

    results, all_ok, missing_with_hints, _ = _check_dependencies_internal()

    if all_ok:
        console.print("[green]All dependencies are already satisfied![/]")
        raise typer.Exit(0)

    # Collect install commands
    commands: list[str] = []
    seen_hints: set[str] = set()

    for result in missing_with_hints:
        if result.install_hint and result.install_hint not in seen_hints:
            seen_hints.add(result.install_hint)
            commands.append(result.install_hint)

    if not commands:
        console.print("[yellow]No automatic install commands available for missing dependencies.[/]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Will run {len(commands)} command(s):[/]")
    for cmd in commands:
        console.print(f"  [cyan]{cmd}[/]")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made[/]")
        raise typer.Exit(0)

    console.print()

    # Execute commands
    failed = 0
    for cmd in commands:
        console.print(f"[bold]Running:[/] {cmd}")
        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            console.print(f"[red]Command failed with exit code {result.returncode}[/]")
            failed += 1
        else:
            console.print("[green]OK[/]")
        console.print()

    # Re-check
    console.print("[dim]Re-checking dependencies...[/]")
    results, all_ok, _, _ = _check_dependencies_internal()

    if all_ok:
        console.print("[green]All dependencies are now satisfied![/]")
    else:
        console.print("[yellow]Some dependencies still missing (run 'voxtype dependencies check' for details)[/]")
        raise typer.Exit(1)
