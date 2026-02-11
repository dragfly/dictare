"""CLI interface for voxtype."""

from __future__ import annotations

import os
import sys
from typing import Annotated

# Disable HuggingFace progress bars globally (must be before any HF imports)
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

import typer

from voxtype import __version__
from voxtype.cli import (
    agent,
    completion,
    config,
    dependencies,
    devices,
    engine,
    execute,
    listen,
    logs,
    misc,
    models,
    speak,
    transcribe,
    tray,
)
from voxtype.cli._helpers import console
from voxtype.config import ConfigError

app = typer.Typer(
    name="voxtype",
    help="Voice-to-text for your terminal",
    add_completion=True,  # Required for shell completion to work at runtime
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,  # Disable rich formatting for errors
)

# Sub-app groups
app.add_typer(completion.app, name="completion")
app.add_typer(models.app, name="models")
app.add_typer(dependencies.app, name="dependencies")
app.add_typer(tray.app, name="tray")
app.add_typer(engine.app, name="engine")
app.add_typer(config.app, name="config")

# Top-level commands (register pattern)
listen.register(app)
speak.register(app)
transcribe.register(app)
execute.register(app)
agent.register(app)
devices.register(app)
logs.register(app)
misc.register(app)

def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"voxtype version {__version__}")
        raise typer.Exit()

@app.callback()
def main_callback(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """voxtype: Voice-to-text for your terminal."""
    pass

def _register_plugins() -> None:
    """Discover and register plugin commands."""
    import logging

    from voxtype.plugins import discover_plugins
    from voxtype.services import ServiceRegistry

    # Create service registry for plugins
    registry = ServiceRegistry()

    for plugin_cls in discover_plugins():
        try:
            plugin = plugin_cls()
            plugin.on_load(registry)

            if commands := plugin.get_commands():
                app.add_typer(commands, name=plugin.name, help=plugin.description)
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Failed to register plugin '{plugin_cls.__name__}': {e}"
            )

# Register plugins at import time (lazy loaded)
_plugins_registered = False

def _ensure_plugins_registered() -> None:
    """Ensure plugins are registered (called once)."""
    global _plugins_registered
    if not _plugins_registered:
        _register_plugins()
        _plugins_registered = True

def main() -> None:
    """Entry point for the CLI."""
    misc.check_python_environment()
    _ensure_plugins_registered()
    try:
        app()
    except ConfigError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
