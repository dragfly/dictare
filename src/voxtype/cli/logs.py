"""Log viewing commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from voxtype.cli._helpers import console

def register(app: typer.Typer) -> None:
    """Register logs command on the main app."""

    @app.command("logs")
    def logs_command(
        name: Annotated[
            str | None,
            typer.Argument(help="Log name: listen, engine, agent.<name>."),
        ] = None,
        follow: Annotated[
            bool,
            typer.Option("--follow", "-f", help="Follow log output (like tail -f)."),
        ] = False,
        raw: Annotated[
            bool,
            typer.Option("--raw", help="Output raw JSON lines."),
        ] = False,
        lines: Annotated[
            int,
            typer.Option("--lines", "-n", help="Number of lines to show."),
        ] = 20,
        path: Annotated[
            bool,
            typer.Option("--path", help="Show log file path instead of content."),
        ] = False,
    ) -> None:
        """View voxtype logs.

        Without arguments, lists all available log files.
        With a name, shows log entries from that log.

        Examples:
            voxtype logs                     # List available log files
            voxtype logs engine              # Show last 20 engine entries
            voxtype logs listen -f           # Follow listen log live
            voxtype logs agent.claude        # Show agent claude logs
            voxtype logs engine --raw        # Output raw JSON
            voxtype logs engine --path       # Show log file path
        """
        from voxtype.logging.jsonl import DEFAULT_LOG_DIR, get_default_log_path

        if name is None:
            # No args: list available log files
            _list_log_files(DEFAULT_LOG_DIR)
            return

        log_path = get_default_log_path(name)

        if path:
            console.print(str(log_path))
            return

        _tail_log(log_path, follow, raw, lines)

def _list_log_files(log_dir: Path) -> None:
    """List available log files in the log directory."""
    from datetime import datetime

    from rich.table import Table

    if not log_dir.exists():
        console.print(f"[yellow]Log directory not found: {log_dir}[/]")
        console.print("[dim]Start voxtype first to create logs.[/]")
        raise typer.Exit(1)

    log_files = list(log_dir.glob("*.jsonl"))

    if not log_files:
        console.print("[yellow]No log files found.[/]")
        raise typer.Exit(0)

    # Sort by modification time (newest first)
    log_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("Name", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Last Modified")

    for log_file in log_files:
        stat = log_file.stat()
        size = stat.st_size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / 1024 / 1024:.1f} MB"

        mtime = datetime.fromtimestamp(stat.st_mtime)
        mtime_str = mtime.strftime("%Y-%m-%d %H:%M")

        name = log_file.stem  # e.g., "listen" or "agent.claude"
        table.add_row(name, size_str, mtime_str)

    console.print(table)
    console.print("\n[dim]Usage: voxtype logs <name> [-f] [--raw] [-n N][/]")

def _tail_log(log_path: Path, follow: bool, raw: bool, lines: int = 20) -> None:
    """Tail a log file with optional follow mode."""
    import json
    import time
    from datetime import datetime

    if not log_path.exists():
        console.print(f"[yellow]Log file not found: {log_path}[/]")
        console.print("[dim]Start voxtype first to create logs.[/]")
        raise typer.Exit(1)

    def format_line(line: str) -> str | None:
        """Format a JSONL line for display."""
        try:
            entry = json.loads(line)
            # Support both "ts" (msg events) and "timestamp" (session events)
            ts = entry.get("ts") or entry.get("timestamp", "")
            level = entry.get("level", "INFO")
            event = entry.get("event", "")

            # Parse and format timestamp
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    ts_str = dt.strftime("%H:%M:%S")
                except Exception:
                    ts_str = ts[:8]
            else:
                ts_str = "??:??:??"

            # Color by level
            level_colors = {"ERROR": "red", "INFO": "green", "DEBUG": "dim"}
            level_color = level_colors.get(level, "white")

            # Format event-specific info
            extra = ""
            if event == "session_start":
                version = entry.get("version") or entry.get("voxtype_version", "?")
                model = entry.get("stt_model")
                agent_id = entry.get("agent_id")
                if agent_id:
                    extra = f"v{version} agent={agent_id}"
                elif model:
                    extra = f"v{version} model={model}"
                else:
                    extra = f"v{version}"
            elif event == "session_end":
                keystrokes = entry.get("total_keystrokes", 0)
                exit_code = entry.get("exit_code", "?")
                extra = f"exit={exit_code} keystrokes={keystrokes}"
            elif event in ("msg_read", "msg_sent"):
                text = entry.get("text", "")
                display_text = text[:80]
                if len(text) > 80:
                    display_text += "..."
                extra = display_text.replace("\n", "\\n")
            elif event == "transcription":
                duration = entry.get("duration_ms", 0)
                text = entry.get("text")
                if text:
                    display = text[:60].replace("\n", "\\n")
                    if len(text) > 60:
                        display += "..."
                    extra = f'{duration:.0f}ms "{display}"'
                else:
                    words = entry.get("words", 0)
                    chars = entry.get("chars", 0)
                    extra = f"{words}w {chars}c {duration:.0f}ms"
            elif event == "transcription_text":
                text = entry.get("text", "")[:60]
                extra = f'"{text}"' + ("..." if len(entry.get("text", "")) > 60 else "")
            elif event == "injection":
                chars = entry.get("chars", 0)
                method = entry.get("method", "?")
                trigger = entry.get("submit_trigger")
                text = entry.get("text")
                if text:
                    display = text[:60].replace("\n", "\\n")
                    if len(text) > 60:
                        display += "..."
                    extra = f'via {method} "{display}"'
                else:
                    extra = f"{chars}c via {method}"
                if trigger:
                    conf = entry.get("submit_confidence", 0)
                    extra += f' [SUBMIT: "{trigger}" {conf:.0%}]'
            elif event == "state_change":
                old = entry.get("old_state", "?")
                new = entry.get("new_state", "?")
                trigger = entry.get("trigger", "?")
                extra = f"{old} -> {new} ({trigger})"
            elif event == "error":
                error = entry.get("error", "")[:50]
                extra = error
            elif event == "vad":
                vad_type = entry.get("type", "?")
                duration = entry.get("duration_ms")
                extra = vad_type + (f" {duration:.0f}ms" if duration else "")

            return f"[dim]{ts_str}[/] [{level_color}]{level:5}[/] [cyan]{event:20}[/] {extra}"
        except json.JSONDecodeError:
            return None

    # Read existing lines
    with open(log_path) as f:
        all_lines = f.readlines()

    # Show last N lines
    start_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

    for line in start_lines:
        line = line.strip()
        if not line:
            continue
        if raw:
            print(line)
        else:
            formatted = format_line(line)
            if formatted:
                console.print(formatted)

    if not follow:
        return

    # Follow mode: watch for new lines
    console.print("[dim]--- Following (Ctrl+C to stop) ---[/]")

    try:
        with open(log_path) as f:
            f.seek(0, 2)

            while True:
                line = f.readline()
                if line:
                    line = line.strip()
                    if raw:
                        print(line)
                    else:
                        formatted = format_line(line)
                        if formatted:
                            console.print(formatted)
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/]")
