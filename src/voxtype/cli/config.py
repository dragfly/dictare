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
        console.print("[dim]Run 'voxtype config edit' to create config file[/]")


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


@app.command("edit")
def config_edit() -> None:
    """Open config file in your editor.

    Uses (in order): config 'editor' field, $VISUAL, $EDITOR, or platform default.
    """
    import os
    import shlex
    import subprocess
    import sys

    config_path = get_config_path()

    # Create config file if it doesn't exist
    if not config_path.exists():
        from voxtype.config import create_default_config

        create_default_config()
        console.print(f"[dim]Created default config: {config_path}[/]")

    # Determine editor: config field > $VISUAL > $EDITOR > platform default
    cfg = load_config(config_path)
    editor_cmd = cfg.editor or os.environ.get("VISUAL") or os.environ.get("EDITOR")

    if editor_cmd:
        parts = shlex.split(editor_cmd)
        parts.append(str(config_path))
        try:
            subprocess.run(parts, check=True)
        except FileNotFoundError:
            console.print(f"[red]Editor not found:[/] {parts[0]}")
            raise typer.Exit(1)
        except subprocess.CalledProcessError as e:
            raise typer.Exit(e.returncode)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-t", str(config_path)])
    else:
        # Linux: xdg-open for graphical, fallback to vi
        for cmd in [["xdg-open", str(config_path)], ["vi", str(config_path)]]:
            try:
                subprocess.run(cmd, check=True)
                break
            except FileNotFoundError:
                continue


