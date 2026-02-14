"""Agent multiplexer - run commands with merged stdin and voxtype input."""

from __future__ import annotations

import json
import os
import platform
import queue
import select
import sys
import termios
import threading
import tty
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from voxtype import __version__
from voxtype.agent.pty_session import (
    PTYSession,
    _get_winsize,
    _set_winsize,  # noqa: F401  — backward-compat re-export
    _write_all,
)
from voxtype.agent.status_bar import StatusBar
from voxtype.pipeline.base import PipelineAction
from voxtype.pipeline.executors import InputExecutor
from voxtype.utils.stats import update_keystrokes

# Session logs directory
SESSIONS_DIR = Path.home() / ".local" / "share" / "voxtype" / "sessions"

# Default engine HTTP server URL (also configurable via [client] in config.toml)
DEFAULT_BASE_URL = "http://127.0.0.1:8770"

def _get_session_log_path(agent_id: str) -> Path:
    """Get path for session log file.

    Format: YYYY-MM-DD_HH-MM-SS_voxtype-X.Y.Z_AGENT.session.jsonl
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{timestamp}_voxtype-{__version__}_{agent_id}.session.jsonl"
    return SESSIONS_DIR / filename

def _write_session_start(
    session_path: Path,
    agent_id: str,
    command: list[str],
    base_url: str,
) -> None:
    """Write session start metadata to log file."""
    metadata = {
        "event": "session_start",
        "timestamp": datetime.now(UTC).isoformat(),
        "voxtype_version": __version__,
        "agent_id": agent_id,
        "command": command,
        "base_url": base_url,
        "cwd": os.getcwd(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "platform_version": platform.release(),
        "user": os.environ.get("USER", "unknown"),
        "shell": os.environ.get("SHELL", "unknown"),
        "term": os.environ.get("TERM", "unknown"),
    }
    with open(session_path, "a") as f:
        f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        f.flush()

def _write_session_end(
    session_path: Path, exit_code: int, total_keystrokes: int = 0
) -> None:
    """Write session end event to log file."""
    metadata = {
        "event": "session_end",
        "timestamp": datetime.now(UTC).isoformat(),
        "exit_code": exit_code,
        "total_keystrokes": total_keystrokes,
    }
    with open(session_path, "a") as f:
        f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        f.flush()

def _log_event(session_path: Path, event: str, data: dict) -> None:
    """Log an event to the session log file (thread-safe)."""
    try:
        log_entry = {
            "event": event,
            "ts": datetime.now(UTC).isoformat(),
            **data,
        }
        with open(session_path, "a") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            f.flush()
    except OSError:
        pass  # Don't crash if logging fails

class KeystrokeCounter:
    """Thread-safe keystroke counter for session statistics."""

    def __init__(self) -> None:
        self._count = 0
        self._lock = threading.Lock()

    def add(self, n: int) -> None:
        with self._lock:
            self._count += n

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

def _read_from_stdin(
    write_queue: queue.Queue,
    stop_event: threading.Event,
    keystroke_counter: KeystrokeCounter | None = None,
) -> None:
    """Read from keyboard in raw mode and put data in queue."""
    try:
        while not stop_event.is_set():
            r, _, _ = select.select([sys.stdin.fileno()], [], [], 0.1)
            if sys.stdin.fileno() in r:
                data = os.read(sys.stdin.fileno(), 1024)
                if not data:
                    break
                # Count keystrokes (bytes received = approximate keystroke count)
                if keystroke_counter:
                    keystroke_counter.add(len(data))
                # Put raw bytes directly in queue
                write_queue.put(("raw", data))
    except (BrokenPipeError, OSError):
        pass

def _poll_active_agent(
    agent_id: str,
    base_url: str,
    stop_event: threading.Event,
    on_status: Callable[[str, str], None],
    poll_interval: float = 3.0,
    sse_connected: threading.Event | None = None,
) -> None:
    """Poll /status to check if this agent is the active one.

    Updates status bar with listening/standby indicator.
    This is the ONLY source of status updates — SSE thread signals
    reconnection via sse_connected event instead of emitting status directly.
    """
    from openvip import Client

    client = Client(base_url, timeout=5)
    last_label: str | None = None

    while not stop_event.is_set():
        # SSE reconnected — force status refresh on next successful poll
        if sse_connected and sse_connected.is_set():
            sse_connected.clear()
            last_label = None

        try:
            status = client.get_status()
            platform = status.platform or {}
            engine_state = platform.get("state", "idle")
            current = platform.get("output", {}).get("current_agent")
            is_active = current == agent_id

            # Determine label based on engine state + active agent
            if is_active and engine_state == "idle":
                label = f"\u25cf {agent_id} \u00b7 idle"
                style = "dim"
            elif is_active:
                label = f"\u25cf {agent_id} \u00b7 listening"
                style = "ok"
            else:
                label = f"\u25cb {agent_id} \u00b7 standby"
                style = "warn"

            if label != last_label:
                last_label = label
                on_status(label, style)
        except (ConnectionRefusedError, OSError, ValueError):
            last_label = None  # Reset so next successful poll forces status update
        stop_event.wait(poll_interval)

def _read_from_sse(
    agent_id: str,
    base_url: str,
    write_queue: queue.Queue,
    stop_event: threading.Event,
    session_path: Path | None = None,
    keystroke_counter: KeystrokeCounter | None = None,
    verbose: bool = False,
    on_status: Callable[[str, str], None] | None = None,
    sse_connected: threading.Event | None = None,
) -> None:
    """Connect to engine SSE and receive OpenVIP messages.

    Uses the OpenVIP SDK's subscribe() with automatic reconnection.

    Args:
        agent_id: Agent identifier.
        base_url: Engine HTTP server base URL (e.g. "http://127.0.0.1:8770").
        write_queue: Queue for writing messages to PTY.
        stop_event: Event to signal thread to stop.
        session_path: Optional session log file path.
        keystroke_counter: Optional keystroke counter for session stats.
        verbose: Log full text in session file.
        on_status: Optional callback(text, style) for status changes.
    """
    from openvip import Client, DuplicateAgentError

    client = Client(base_url)
    msg_count = 0
    url = f"{base_url}/agents/{agent_id}/messages"

    # Executor pipeline for x_input messages
    _openvip_meta: dict[str, Any] = {}

    def _enqueue_input(text: str, submit: bool) -> None:
        msg: dict[str, Any] = {"text": text}
        if submit:
            msg["submit"] = True
        msg.update(_openvip_meta)
        write_queue.put(("msg", msg))

    input_executor = InputExecutor(write_fn=_enqueue_input)

    def _on_connect() -> None:
        if sse_connected:
            sse_connected.set()  # Signal poll thread to refresh status
        if session_path:
            _log_event(session_path, "sse_connected", {"url": url})

    def _on_disconnect(exc: Exception | None) -> None:
        if not exc:
            return
        http_code = getattr(exc, "code", None)
        if on_status:
            if http_code:
                on_status(f"\u26a0 {agent_id} \u00b7 HTTP {http_code}, reconnecting...", "error")
            else:
                on_status(f"\u26a0 {agent_id} \u00b7 reconnecting...", "error")
        if session_path:
            event = "sse_http_error" if http_code else "sse_connect_error"
            log_data: dict[str, Any] = {"error": str(exc)}
            if http_code:
                log_data["code"] = http_code
            _log_event(session_path, event, log_data)

    try:
        for msg in client.subscribe(
            agent_id,
            reconnect=True,
            stop=stop_event.is_set,
            on_connect=_on_connect,
            on_disconnect=_on_disconnect,
        ):
            if stop_event.is_set():
                break

            # Skip partial transcriptions
            if msg.partial:
                continue

            msg_id = str(msg.id) if msg.id else None
            msg_ts = msg.timestamp.isoformat() if msg.timestamp else None

            # Set openvip metadata for the executor's write_fn
            _openvip_meta.clear()
            _openvip_meta["openvip_id"] = msg_id
            _openvip_meta["openvip_ts"] = msg_ts

            msg_count += 1
            if session_path:
                text = msg.text or ""
                _log_event(session_path, "msg_read", {
                    "seq": msg_count,
                    "text": text if verbose else text[:50],
                    "openvip_id": msg_id,
                    "keystrokes": keystroke_counter.count if keystroke_counter else 0,
                })

            # Process through executor pipeline (needs raw dict for x_input access)
            msg_dict = msg.to_dict()
            result = input_executor.process(msg_dict)
            if result.action == PipelineAction.PASS:
                # No x_input — enqueue as plain text
                write_queue.put(("msg", {
                    "text": msg.text or "",
                    "openvip_id": msg_id,
                    "openvip_ts": msg_ts,
                }))

    except DuplicateAgentError:
        err_msg = f"Agent '{agent_id}' already connected"
        if on_status:
            on_status(f"\u2716 {err_msg}", "error")
        if session_path:
            _log_event(session_path, "sse_duplicate", {"agent_id": agent_id})
        write_queue.put(("error", err_msg))  # type: ignore[arg-type]

    if session_path:
        _log_event(session_path, "sse_disconnected", {"total_messages": msg_count})

def _write_to_pty(
    master_fd: int,
    write_queue: queue.Queue,
    stop_event: threading.Event,
    session_path: Path | None = None,
    keystroke_counter: KeystrokeCounter | None = None,
    verbose: bool = False,
) -> None:
    """Consume from queue and write to PTY.

    This is the ONLY thread that writes to master_fd, ensuring serialization.
    Logs every message sent for debugging.
    """
    # Alt+Enter for visual newline (ESC + CR)
    alt_enter = b"\x1b\r"
    enter_key = b"\r"
    msg_count = 0

    while not stop_event.is_set():
        try:
            # Block with timeout so we can check stop_event
            item = write_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        msg_type, data = item

        try:
            if msg_type == "error":
                # Fatal error from SSE thread — log and continue
                # (status bar already updated by SSE thread)
                if session_path:
                    _log_event(session_path, "agent_error", {"error": data})
                continue
            elif msg_type == "raw":
                # Raw bytes from stdin - write directly, handle short writes
                _write_all(master_fd, data)
            elif msg_type == "msg":
                msg_count += 1
                # Parsed JSONL message from file
                text = data.get("text", "")
                bytes_written = 0

                # Write text and control sequences as SEPARATE writes.
                # Escape sequences (\x1b) must not be in the same buffer
                # as text — the slave's input parser treats ESC as the
                # start of a key sequence and discards preceding text.
                if text:
                    has_visual_newline = text.endswith("\n")
                    if has_visual_newline:
                        text = text.rstrip("\n")

                    if text:
                        text_bytes = text.encode()
                        bytes_written += _write_all(master_fd, text_bytes)
                        termios.tcdrain(master_fd)

                    # Alt+Enter for visual newline (contains ESC — must be separate).
                    # 10ms grace period so the slave reads text before ESC arrives.
                    if has_visual_newline:
                        stop_event.wait(0.01)
                        bytes_written += _write_all(master_fd, alt_enter)
                        termios.tcdrain(master_fd)

                # Submit enter (plain CR — no ESC, safe to write anytime)
                if data.get("submit"):
                    stop_event.wait(0.01)
                    bytes_written += _write_all(master_fd, enter_key)
                    termios.tcdrain(master_fd)

                # Log message AFTER successful write AND drain
                if session_path:
                    text = data.get("text", "")
                    _log_event(session_path, "msg_sent", {
                        "seq": msg_count,
                        "text": text if verbose else text[:50],
                        "bytes": bytes_written,
                        "openvip_id": data.get("openvip_id"),
                        "openvip_ts": data.get("openvip_ts"),
                        "keystrokes": keystroke_counter.count if keystroke_counter else 0,
                    })
        except (BrokenPipeError, OSError) as e:
            if session_path:
                _log_event(session_path, "writer_error", {"error": str(e), "msg_count": msg_count})
            break

def run_agent(
    agent_id: str,
    command: list[str],
    quiet: bool = False,
    verbose: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    status_bar: bool = True,
    clear_on_start: bool = True,
) -> int:
    """Run a command with multiplexed input from stdin and voxtype SSE.

    Connects to the engine's HTTP server via SSE to receive OpenVIP messages.
    The SSE connection itself registers the agent with the engine.

    Args:
        agent_id: Agent identifier (e.g., 'claude').
        command: Command and arguments to run.
        quiet: Suppress info messages.
        verbose: Log full text in session file (not truncated to 50 chars).
        base_url: Engine HTTP server base URL.
        status_bar: Show persistent status bar on last terminal row.
        clear_on_start: Clear terminal before launching child process.

    Returns:
        Exit code of the process.
    """
    # Create session log
    session_path = _get_session_log_path(agent_id)
    _write_session_start(session_path, agent_id, command, base_url)

    if not quiet:
        print(f"[voxtype {__version__}] Agent: {agent_id}", file=sys.stderr)
        print(f"[voxtype {__version__}] Server: {base_url}", file=sys.stderr)
        print(f"[voxtype {__version__}] Session: {session_path}", file=sys.stderr)
        print(f"[voxtype {__version__}] Running: {' '.join(command)}", file=sys.stderr)

    # Save original terminal settings
    old_settings = None
    if sys.stdin.isatty():
        old_settings = termios.tcgetattr(sys.stdin.fileno())

    rows, cols = _get_winsize()
    sbar = StatusBar(agent_id) if status_bar else None

    def on_output(data: bytes) -> None:
        os.write(sys.stdout.fileno(), data)
        if sbar:
            sbar.after_child_output()

    def on_resize(r: int, c: int) -> None:
        if sbar:
            sbar.on_resize(r, c)

    session = PTYSession(
        command, rows, cols,
        on_output=on_output,
        on_resize=on_resize,
        reserve_rows=1 if sbar else 0,
    )

    try:
        # Clear terminal for clean start (before launching child process
        # so that any immediate errors from the child are visible)
        if clear_on_start:
            sys.stdout.buffer.write(b"\x1b[2J\x1b[H")
            sys.stdout.buffer.flush()

        session.start()

        # Init status bar before raw mode
        if sbar:
            sbar.init(rows, cols)

        # Put terminal in raw mode
        if old_settings:
            tty.setraw(sys.stdin.fileno())

        stop_event = threading.Event()

        # Create thread-safe queue for serialized writes to PTY
        write_queue: queue.Queue = queue.Queue()

        # Create keystroke counter for session statistics
        keystroke_counter = KeystrokeCounter()

        master_fd = session.master_fd

        # Start producer threads (read from stdin/SSE, put in queue)
        stdin_thread = threading.Thread(
            target=_read_from_stdin,
            args=(write_queue, stop_event, keystroke_counter),
            daemon=True,
        )
        # Shared event: SSE thread signals reconnection, poll thread refreshes status
        sse_connected_event = threading.Event()
        # SSE-based IPC: connect to engine HTTP server
        sse_thread = threading.Thread(
            target=_read_from_sse,
            args=(agent_id, base_url, write_queue, stop_event, session_path, keystroke_counter, verbose),
            kwargs={"on_status": sbar.update if sbar else None, "sse_connected": sse_connected_event},
            daemon=True,
        )
        # Start consumer thread (read from queue, write to PTY)
        writer_thread = threading.Thread(
            target=_write_to_pty,
            args=(master_fd, write_queue, stop_event, session_path, keystroke_counter, verbose),
            daemon=True,
        )
        # Poll engine to track active agent (status bar: listening/standby)
        if sbar:
            poll_thread = threading.Thread(
                target=_poll_active_agent,
                args=(agent_id, base_url, stop_event, sbar.update),
                kwargs={"sse_connected": sse_connected_event},
                daemon=True,
            )

        stdin_thread.start()
        sse_thread.start()
        writer_thread.start()
        if sbar:
            poll_thread.start()

        exit_code = session.run_output_loop(
            on_idle=sbar.check_redraw if sbar else None,
        )
        stop_event.set()

        # Log session end with total keystrokes
        _write_session_end(session_path, exit_code, keystroke_counter.count)

        # Update lifetime stats with keystroke count
        if keystroke_counter.count > 0:
            update_keystrokes(keystroke_counter.count)
        return exit_code

    finally:
        # Reset scroll region before restoring terminal
        if sbar:
            sbar.cleanup()

        # Restore terminal settings
        if old_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

        session.cleanup()
