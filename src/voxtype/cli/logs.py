"""voxtype logs — human-readable view of structured engine logs."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(hidden=True)

LEVEL_COLORS = {
    "DEBUG": "dim",
    "INFO": "cyan",
    "WARNING": "yellow",
    "ERROR": "red bold",
    "CRITICAL": "red bold",
}

def _format_line(raw: str) -> str | None:
    """Parse a JSONL line and return a human-readable string, or None to skip."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        entry = json.loads(raw)
    except json.JSONDecodeError:
        return raw  # pass through non-JSON lines as-is

    ts = entry.get("ts", "")
    # Shorten ISO timestamp → HH:MM:SS
    if "T" in ts:
        ts = ts.split("T")[1][:8]

    level = entry.get("level", "INFO").upper()
    event = entry.get("event", entry.get("message", ""))
    logger = entry.get("logger", "")

    # Collect extra fields (skip known structural ones)
    skip = {"ts", "level", "event", "message", "logger", "version", "pid"}
    extras = {k: v for k, v in entry.items() if k not in skip and v is not None}
    extras_str = "  " + "  ".join(f"{k}={v}" for k, v in extras.items()) if extras else ""

    short_logger = logger.split(".")[-1] if logger else ""
    logger_str = f"  [{short_logger}]" if short_logger else ""

    return f"{ts}  {level:<8} {event}{logger_str}{extras_str}"

def _print_line(line: str, use_rich: bool) -> None:
    if not use_rich:
        print(line)
        return
    from rich.console import Console

    console = Console()
    # Colorize by level
    level = ""
    for lvl in LEVEL_COLORS:
        if f"  {lvl}" in line:
            level = lvl
            break
    color = LEVEL_COLORS.get(level, "")
    if color and level in line:
        # Bold the level token
        colored = line.replace(f"  {level}", f"  [{color}]{level}[/]", 1)
        console.print(colored, highlight=False)
    else:
        console.print(line, highlight=False)

def register(app: typer.Typer) -> None:
    """Register the logs command on the main app."""

    @app.command("logs")
    def logs_command(
        follow: Annotated[bool, typer.Option("--follow", "-f", help="Follow log output")] = False,
        last: Annotated[int, typer.Option("--last", "-n", help="Show last N lines")] = 50,
        name: Annotated[str, typer.Option("--name", help="Log name (engine, agent.*)")] = "engine",
        raw: Annotated[bool, typer.Option("--raw", help="Output raw JSONL (pipe-friendly)")] = False,
    ) -> None:
        """Show engine logs in human-readable format.

        Examples:
            voxtype logs              # last 50 lines
            voxtype logs -f           # follow (like tail -f)
            voxtype logs -n 100       # last 100 lines
            voxtype logs --raw | jq . # raw JSONL for scripting
        """
        from voxtype.logging.setup import DEFAULT_LOG_DIR

        log_path = DEFAULT_LOG_DIR / f"{name}.jsonl"

        if not log_path.exists():
            typer.echo(f"No log file found: {log_path}", err=True)
            typer.echo(f"Start the engine first: voxtype engine start", err=True)
            raise typer.Exit(1)

        use_rich = not raw and sys.stdout.isatty()

        if raw:
            # Raw mode: just output JSONL lines, pipe-friendly
            lines = log_path.read_text().splitlines()
            for line in lines[-last:]:
                print(line)
            if follow:
                with open(log_path) as f:
                    f.seek(0, 2)  # seek to end
                    while True:
                        line = f.readline()
                        if line:
                            print(line.rstrip())
                            sys.stdout.flush()
                        else:
                            time.sleep(0.1)
            return

        # Human-readable mode
        lines = log_path.read_text().splitlines()
        for raw_line in lines[-last:]:
            formatted = _format_line(raw_line)
            if formatted:
                _print_line(formatted, use_rich)

        if follow:
            with open(log_path) as f:
                f.seek(0, 2)  # seek to end
                while True:
                    raw_line = f.readline()
                    if raw_line:
                        formatted = _format_line(raw_line)
                        if formatted:
                            _print_line(formatted, use_rich)
                            sys.stdout.flush()
                    else:
                        time.sleep(0.1)
