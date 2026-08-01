"""dictare logs — human-readable view of structured engine logs."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Iterator
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

def _parse_line(raw: str) -> dict | None:
    """Parse a JSONL line into a dict, or None for blank lines."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"event": raw}  # pass through non-JSON lines as-is

def _matches_source(entry: dict, source_filter: str) -> bool:
    """Return True if entry matches the source filter."""
    if not source_filter:
        return True
    return entry.get("source", "") == source_filter

def _format_entry(entry: dict) -> str:
    """Format a parsed log entry as a human-readable string."""
    ts = entry.get("ts", "")
    # Shorten ISO timestamp → HH:MM:SS
    if "T" in ts:
        ts = ts.split("T")[1][:8]

    level = entry.get("level", "INFO").upper()
    event = entry.get("event", entry.get("message", ""))
    logger_name = entry.get("logger", "")
    source = entry.get("source", "")

    # Collect extra fields (skip known structural ones)
    skip = {"ts", "level", "event", "message", "logger", "version", "pid", "source"}
    extras = {k: v for k, v in entry.items() if k not in skip and v is not None}
    extras_str = "  " + "  ".join(f"{k}={v}" for k, v in extras.items()) if extras else ""

    short_logger = logger_name.split(".")[-1] if logger_name else ""
    logger_str = f"  [{short_logger}]" if short_logger else ""
    source_str = f"  <{source}>" if source else ""

    return f"{ts}  {level:<8} {event}{source_str}{logger_str}{extras_str}"

def _format_line(raw: str, source_filter: str = "") -> str | None:
    """Parse a JSONL line and return a human-readable string, or None to skip."""
    entry = _parse_line(raw)
    if entry is None:
        return None
    if not _matches_source(entry, source_filter):
        return None
    return _format_entry(entry)

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


def _iter_lines_reverse(path: Path, chunk_size: int = 64 * 1024) -> Iterator[str]:
    """Yield lines newest-first without loading the whole file into memory."""
    with path.open("rb") as file:
        position = file.seek(0, 2)
        remainder = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            file.seek(position)
            parts = (file.read(read_size) + remainder).split(b"\n")
            if position > 0:
                remainder = parts.pop(0)
            else:
                remainder = b""
            for raw_line in reversed(parts):
                if raw_line:
                    yield raw_line.decode("utf-8", errors="replace")


def _tail_log_lines(
    log_path: Path,
    last: int,
    predicate: Callable[[str], bool] | None = None,
) -> list[str]:
    """Return the newest matching lines across a log and its rotations."""
    if last <= 0:
        return []
    newest_first: list[str] = []
    candidates = [log_path, *(log_path.with_name(f"{log_path.name}.{i}") for i in range(1, 6))]
    for candidate in candidates:
        if not candidate.exists():
            continue
        for line in _iter_lines_reverse(candidate):
            if predicate is None or predicate(line):
                newest_first.append(line)
                if len(newest_first) >= last:
                    return list(reversed(newest_first))
    return list(reversed(newest_first))

def _show_plain_log(log_path: Path, follow: bool, last: int) -> None:
    """Show a plain-text log file (not JSONL)."""
    if not log_path.exists():
        typer.echo(f"No log file found: {log_path}", err=True)
        raise typer.Exit(1)

    for line in _tail_log_lines(log_path, last):
        print(line)

    if follow:
        with open(log_path) as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    print(line.rstrip())
                    sys.stdout.flush()
                else:
                    time.sleep(0.1)

def register(app: typer.Typer) -> None:
    """Register the logs command on the main app."""

    @app.command("logs")
    def logs_command(
        follow: Annotated[bool, typer.Option("--follow", "-f", help="Follow log output")] = False,
        last: Annotated[int, typer.Option("--last", "-n", help="Show last N lines")] = 50,
        name: Annotated[str, typer.Option("--name", help="Log name (engine, agent.*)")] = "engine",
        source: Annotated[str, typer.Option("--source", "-s", help="Filter by source (engine, tray)")] = "",
        raw: Annotated[bool, typer.Option("--raw", help="Output raw JSONL (pipe-friendly)")] = False,
        tts: Annotated[bool, typer.Option("--tts", help="Show TTS worker log (plain text)")] = False,
    ) -> None:
        """Show engine logs in human-readable format.

        Examples:
            dictare logs              # last 50 lines (all sources)
            dictare logs -f           # follow (like tail -f)
            dictare logs --tts        # TTS worker log
            dictare logs --tts -f     # follow TTS worker log
            dictare logs -s tray      # only tray entries
            dictare logs -s engine    # only engine entries
            dictare logs -n 100       # last 100 lines
            dictare logs --raw | jq . # raw JSONL for scripting
        """
        from dictare.logging.setup import DEFAULT_LOG_DIR

        if tts:
            _show_plain_log(DEFAULT_LOG_DIR / "tts-worker.log", follow, last)
            return

        if name == "engine" and source == "tray":
            log_path = DEFAULT_LOG_DIR / "tray.jsonl"
        else:
            log_path = DEFAULT_LOG_DIR / f"{name}.jsonl"

        if not log_path.exists():
            typer.echo(f"No log file found: {log_path}", err=True)
            typer.echo("Start the engine first: dictare serve", err=True)
            raise typer.Exit(1)

        use_rich = not raw and sys.stdout.isatty()

        if raw:
            # Raw mode: just output JSONL lines, pipe-friendly
            def _raw_matches(line: str) -> bool:
                entry = _parse_line(line)
                return bool(entry and _matches_source(entry, source))

            for line in _tail_log_lines(log_path, last, _raw_matches):
                print(line)
            if follow:
                with open(log_path) as f:
                    f.seek(0, 2)  # seek to end
                    while True:
                        line = f.readline()
                        if line:
                            entry = _parse_line(line)
                            if entry and _matches_source(entry, source):
                                print(line.rstrip())
                                sys.stdout.flush()
                        else:
                            time.sleep(0.1)
            return

        # Human-readable mode
        def _human_matches(raw_line: str) -> bool:
            entry = _parse_line(raw_line)
            return bool(entry and _matches_source(entry, source))

        for raw_line in _tail_log_lines(log_path, last, _human_matches):
            formatted = _format_line(raw_line, source)
            if formatted:
                _print_line(formatted, use_rich)

        if follow:
            with open(log_path) as f:
                f.seek(0, 2)  # seek to end
                while True:
                    raw_line = f.readline()
                    if raw_line:
                        formatted = _format_line(raw_line, source)
                        if formatted:
                            _print_line(formatted, use_rich)
                            sys.stdout.flush()
                    else:
                        time.sleep(0.1)
