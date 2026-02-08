"""Configuration management commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from voxtype.cli._helpers import console
from voxtype.config import (
    get_config_path,
    get_config_value,
    list_config_keys,
    load_config,
    set_config_value,
)

app = typer.Typer(help="Manage configuration.", no_args_is_help=True)

@app.command("list")
def config_list() -> None:
    """List all configuration options with current values."""
    _show_config_list()

def _show_config_list() -> None:
    """Show all config keys in a table."""
    config_path = get_config_path()
    cfg = load_config()

    table = Table(
        show_header=True,
        header_style="bold",
        title="Configuration",
        title_style="bold green",
        expand=False,
    )
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="yellow")
    table.add_column("Env Override", style="dim")

    for key, type_name, default, description, env_var in list_config_keys():
        try:
            current = get_config_value(key, cfg)
            # Format value for display
            if current is None:
                value_str = "[dim]null[/]"
            elif isinstance(current, bool):
                value_str = "[green]true[/]" if current else "[red]false[/]"
            else:
                value_str = str(current)
        except KeyError:
            value_str = "[red]error[/]"

        table.add_row(key, value_str, env_var)

    console.print(table)

    if config_path.exists():
        console.print(f"[dim]Config file: {config_path}[/]")
    else:
        console.print(f"[dim]Config file: {config_path} (not created, using defaults)[/]")
        console.print("[dim]Run 'voxtype init' to create config file[/]")

@app.command("get")
def config_get(
    ctx: typer.Context,
    key: Annotated[str | None, typer.Argument(help="Config key (e.g., stt.model)")] = None,
) -> None:
    """Get a configuration value."""
    if key is None:
        import click

        click.echo(ctx.get_help())
        raise typer.Exit(0)

    try:
        value = get_config_value(key)
        console.print(value)
    except KeyError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

@app.command("set")
def config_set(
    ctx: typer.Context,
    key: Annotated[str | None, typer.Argument(help="Config key (e.g., stt.model)")] = None,
    value: Annotated[str | None, typer.Argument(help="Value to set")] = None,
) -> None:
    """Set a configuration value."""
    if key is None or value is None:
        import click

        click.echo(ctx.get_help())
        raise typer.Exit(0)

    try:
        set_config_value(key, value)
        console.print(f"[green]✓[/] Set [cyan]{key}[/] = [yellow]{value}[/]")
    except KeyError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Invalid value:[/] {e}")
        raise typer.Exit(1)

@app.command("path")
def config_path_cmd() -> None:
    """Show config file path."""
    console.print(get_config_path())

@app.command("shortcuts")
def config_shortcuts() -> None:
    """Configure keyboard shortcuts interactively.

    Opens an interactive UI to set global keyboard shortcuts for voxtype commands.
    Shortcuts work system-wide while voxtype is running.
    """
    from voxtype.ui import configure_shortcuts

    configure_shortcuts()
