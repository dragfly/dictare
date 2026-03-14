"""Agent multiplexer - run commands with merged stdin and dictare input."""

from __future__ import annotations

import json
import logging
import os
import platform
import queue
import re as _re
import select
import sys
import termios
import threading
import tty
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openvip.models import Transcription

from dictare import __version__
from dictare.agent.pty_session import (
    PTYSession,
    _get_winsize,
    _set_winsize,  # noqa: F401  — backward-compat re-export
    _write_all,
)
from dictare.agent.status_bar import StatusBar
from dictare.logging.setup import setup_logging
from dictare.pipeline.base import PipelineAction
from dictare.pipeline.executors import InputExecutor
from dictare.utils.stats import update_keystrokes

logger = logging.getLogger(__name__)

# Escape sequences that trigger a reactive status bar redraw:
# - ESC[2J  = erase screen (Claude Code Ctrl+O, resize)
# - ESC[J   = erase below cursor (Codex startup: cursor at row 1 → wipes all)
# - ESC[r   = DECSTBM reset (Codex resets our scroll region)
_SCREEN_CLEAR = b"\x1b[2J"
_ERASE_BELOW = b"\x1b[J"
_DECSTBM_RESET = b"\x1b[r"
# Regex to detect child-initiated DECSTBM set (ESC[N;Mr) — NOT the bare reset (ESC[r).
# If the child sets its own scroll region, we must back off.
_DECSTBM_SET_RE = _re.compile(rb'\x1b\[\d+;\d+r')

# Session logs directory
SESSIONS_DIR = Path.home() / ".local" / "share" / "dictare" / "sessions"

# Default engine HTTP server URL (also configurable via [client] in config.toml)
DEFAULT_BASE_URL = "http://127.0.0.1:8770/openvip"

def _get_session_log_path(agent_id: str) -> Path:
    """Get path for session log file.

    Format: YYYY-MM-DD_HH-MM-SS_dictare-X.Y.Z_AGENT.session.jsonl
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{timestamp}_dictare-{__version__}_{agent_id}.session.jsonl"
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
        "dictare_version": __version__,
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

# Default claim key byte sequences (Ctrl+\).
# Kept as module constants for backward-compatible test imports.
_CTRL_BACKSLASH = b"\x1c"
_CTRL_BACKSLASH_CSI_U = b"\x1b[92;5u"

# Terminal focus reporting escape sequences (xterm extension, widely supported)
_FOCUS_ENABLE = b"\x1b[?1004h"
_FOCUS_DISABLE = b"\x1b[?1004l"
_FOCUS_IN = b"\x1b[I"
_FOCUS_OUT = b"\x1b[O"

def _parse_claim_key(key_str: str) -> tuple[bytes, bytes]:
    """Parse a claim key string into (raw_byte, csi_u_bytes).

    Supports ``ctrl+<char>`` format.  For any ``ctrl+X``:
    - Raw mode byte: ``ord(X) & 0x1F``
    - Kitty CSI u:   ``ESC[{ord(X)};5u``

    Args:
        key_str: Key specification, e.g. ``"ctrl+\\\\"`` or ``"ctrl+]"``.

    Returns:
        Tuple of (raw_byte, csi_u_bytes).

    Raises:
        ValueError: If the format is not recognized.
    """
    key_str = key_str.strip().lower()
    if not key_str.startswith("ctrl+") or len(key_str) < 6:
        raise ValueError(
            f"Unsupported claim_key format: {key_str!r}. "
            "Expected 'ctrl+<char>' (e.g. 'ctrl+\\\\', 'ctrl+]')"
        )
    char = key_str[5:]
    if len(char) != 1:
        raise ValueError(
            f"Unsupported claim_key character: {char!r}. "
            "Expected a single character after 'ctrl+'"
        )
    raw = bytes([ord(char) & 0x1F])
    csi_u = f"\x1b[{ord(char)};5u".encode()
    return raw, csi_u

def _strip_claim_key(data: bytes, raw: bytes, csi_u: bytes) -> tuple[bytes, bool]:
    """Remove all claim key variants from *data*.

    Returns (cleaned_data, found) where *found* is True if any
    claim key sequence was present.
    """
    found = False
    if csi_u in data:
        data = data.replace(csi_u, b"")
        found = True
    if raw in data:
        data = data.replace(raw, b"")
        found = True
    return data, found

# Backward-compatible alias used by existing tests
def _strip_ctrl_backslash(data: bytes) -> tuple[bytes, bool]:
    """Remove Ctrl+\\\\ from *data* (backward-compatible wrapper)."""
    return _strip_claim_key(data, _CTRL_BACKSLASH, _CTRL_BACKSLASH_CSI_U)

def _strip_focus_events(data: bytes) -> tuple[bytes, bool | None]:
    """Remove focus-in/out escape sequences from *data*.

    Returns (cleaned_data, focused) where *focused* is:
    - True if the last focus event was focus-in
    - False if the last focus event was focus-out
    - None if no focus events were found
    """
    focused: bool | None = None
    if _FOCUS_IN in data or _FOCUS_OUT in data:
        # Determine last focus state (in case both appear in one read)
        last_in = data.rfind(_FOCUS_IN)
        last_out = data.rfind(_FOCUS_OUT)
        if last_in > last_out:
            focused = True
        elif last_out > last_in:
            focused = False
        elif last_in >= 0:
            focused = True  # both equal → only _FOCUS_IN present
        data = data.replace(_FOCUS_IN, b"").replace(_FOCUS_OUT, b"")
    return data, focused

def _report_focus(agent_id: str, base_url: str, focused: bool) -> None:
    """POST focus state to engine (fire-and-forget, background thread)."""
    def _do() -> None:
        import json as _json
        import urllib.request

        url = base_url.rstrip("/").rsplit("/openvip", 1)[0]
        url = f"{url}/api/agents/{agent_id}/focus"
        body = _json.dumps({"focused": focused}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass

    threading.Thread(target=_do, daemon=True).start()

def _read_from_stdin(
    write_queue: queue.Queue,
    stop_event: threading.Event,
    keystroke_counter: KeystrokeCounter | None = None,
    agent_id: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    session_path: Path | None = None,
    claim_key_raw: bytes = _CTRL_BACKSLASH,
    claim_key_csi_u: bytes = _CTRL_BACKSLASH_CSI_U,
) -> None:
    """Read from keyboard in raw mode and put data in queue.

    When *agent_id* is set, the claim key is intercepted and sends
    ``output.set_agent:<agent_id>`` to the engine, making this
    terminal the active voice target.  The keystroke is consumed
    and never forwarded to the child process.

    Supports both classic raw-mode byte and the kitty keyboard
    protocol CSI u sequence.
    """
    try:
        while not stop_event.is_set():
            r, _, _ = select.select([sys.stdin.fileno()], [], [], 0.1)
            if sys.stdin.fileno() in r:
                data = os.read(sys.stdin.fileno(), 1024)
                if not data:
                    break

                # Strip focus events (terminal focus reporting)
                if agent_id:
                    data, focus_state = _strip_focus_events(data)
                    if focus_state is not None:
                        _report_focus(agent_id, base_url, focus_state)
                        if not data:
                            continue

                # Intercept claim key to claim this agent as active
                if agent_id:
                    data, found = _strip_claim_key(data, claim_key_raw, claim_key_csi_u)
                    if found:
                        if session_path:
                            _log_event(session_path, "claim_key", {
                                "agent_id": agent_id,
                                "base_url": base_url,
                            })
                        _claim_agent(agent_id, base_url)
                        if not data:
                            continue

                # Count keystrokes (bytes received = approximate keystroke count)
                if keystroke_counter:
                    keystroke_counter.add(len(data))
                # Put raw bytes directly in queue
                write_queue.put(("raw", data))
    except (BrokenPipeError, OSError):
        pass

def _claim_agent(agent_id: str, base_url: str) -> None:
    """Send ``output.set_agent:<agent_id>`` to the engine (fire-and-forget)."""
    def _do() -> None:
        try:
            from openvip import Client

            client = Client(base_url, timeout=3)
            client.control(f"output.set_agent:{agent_id}")
        except Exception:
            pass  # Best-effort; engine may be unreachable

    threading.Thread(target=_do, daemon=True).start()

def _stream_active_agent(
    agent_id: str,
    base_url: str,
    stop_event: threading.Event,
    on_status: Callable[[str, str], None],
) -> None:
    """Subscribe to /status/stream SSE to track active agent.

    Updates status bar with listening/off/standby indicator.
    Push-based: engine sends status on every state transition and
    agent connect/disconnect — no polling needed.
    """
    from openvip import Client

    from dictare.status import resolve_display_state

    client = Client(base_url, timeout=5)
    last_key: tuple[str, str] | None = None

    def _on_disconnect(exc: Exception | None) -> None:
        nonlocal last_key
        if exc:
            last_key = None  # Force refresh on reconnect

    for status in client.subscribe_status(
        reconnect=True,
        stop=stop_event.is_set,
        on_disconnect=_on_disconnect,
    ):
        if stop_event.is_set():
            break

        platform = status.platform or {}
        state, style = resolve_display_state(platform, agent_id)
        dot = "●" if state in ("listening", "recording", "off", "muted") else "○"
        if state == "recording":
            # Red text for "recording", revert to bar style after
            label = f"{dot} {agent_id} \u00b7 \x1b[38;5;210mrecording\x1b[38;5;114m"
        else:
            label = f"{dot} {agent_id} \u00b7 {state}"

        key = (label, style)
        if key != last_key:
            last_key = key
            on_status(label, style)

def _read_from_sse(
    agent_id: str,
    base_url: str,
    write_queue: queue.Queue,
    stop_event: threading.Event,
    session_path: Path | None = None,
    keystroke_counter: KeystrokeCounter | None = None,
    verbose: bool = False,
    on_status: Callable[[str, str], None] | None = None,
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
        if session_path:
            _log_event(session_path, "sse_connected", {"agent_id": agent_id})

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

            if not isinstance(msg, Transcription):
                continue

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
                    "text": text if verbose else (text[:20] + "[...]" if len(text) > 20 else text),
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
                # Fatal error from SSE thread — stop the session
                # (status bar already updated by SSE thread)
                if session_path:
                    _log_event(session_path, "agent_error", {"error": data})
                stop_event.set()
                break
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
                        "text": text if verbose else (text[:20] + "[...]" if len(text) > 20 else text),
                        "bytes": bytes_written,
                        "openvip_id": data.get("openvip_id"),
                        "openvip_ts": data.get("openvip_ts"),
                        "keystrokes": keystroke_counter.count if keystroke_counter else 0,
                    })
        except (BrokenPipeError, OSError) as e:
            if session_path:
                _log_event(session_path, "writer_error", {"error": str(e), "msg_count": msg_count})
            break

def _print_session_summary(base_url: str) -> None:
    """Fetch session stats from the engine and print a summary to stderr."""
    import random
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base_url}/status", timeout=2) as resp:
            data = json.loads(resp.read())
            platform = data.get("platform", {})
            stats = platform.get("stats", {})
    except Exception:
        return

    count = stats.get("transcriptions", 0)
    if count == 0:
        return

    words = stats.get("words", 0)
    chars = stats.get("chars", 0)
    audio = stats.get("audio_seconds", 0.0)
    stt = stats.get("transcription_seconds", 0.0)
    injection = stats.get("injection_seconds", 0.0)
    processing = audio + stt + injection

    # Effective WPM
    processing_min = processing / 60
    effective_wpm = words / processing_min if processing_min > 0 else 0

    # Time saved vs typing (assume 40 WPM typing)
    typing_wpm = 40
    typing_time = (chars / (typing_wpm * 5)) * 60  # seconds
    time_saved = typing_time - processing

    # Two-column layout (plain text, no rich dependency)
    col1 = [
        ("Transcriptions", str(count)),
        ("Words", str(words)),
        ("Characters", str(chars)),
        ("Effective WPM", f"{effective_wpm:.0f}"),
    ]
    col2 = [
        ("Audio", f"{audio:.1f}s"),
        ("STT", f"{stt:.1f}s"),
        ("Injection", f"{injection:.1f}s"),
        ("Processing", f"{processing:.1f}s"),
    ]

    # Format columns
    w1k = max(len(k) for k, _ in col1)
    w1v = max(len(v) for _, v in col1)
    w2k = max(len(k) for k, _ in col2)
    w2v = max(len(v) for _, v in col2)

    print(file=sys.stderr)
    header = f" {'Output':<{w1k + w1v + 2}}       {'Timing'}"
    print(header, file=sys.stderr)
    for (k1, v1), (k2, v2) in zip(col1, col2):
        line = f" {k1:<{w1k}}  {v1:>{w1v}}       {k2:<{w2k}}  {v2:>{w2v}}"
        print(line, file=sys.stderr)

    # Time saved phrase
    if time_saved > 0:
        phrases = [
            "{time} extra for coffee.",
            "Saved you {time}. You're welcome.",
            "{time} back in your pocket.",
            "{time} gained. Use them wisely!",
        ]
        if time_saved >= 60:
            time_str = f"{time_saved / 60:.1f} minutes"
        else:
            time_str = f"{time_saved:.0f} seconds"
        print(file=sys.stderr)
        print(random.choice(phrases).format(time=time_str), file=sys.stderr)

    # Lifetime stats
    try:
        from dictare.stats import load_stats
        lifetime = load_stats()
        lifetime_saved = lifetime.get("total_time_saved_seconds", 0)
        sessions = lifetime.get("sessions", 0)
        first_use = lifetime.get("first_use", "")
        if lifetime_saved > 0 and first_use:
            from datetime import datetime
            if lifetime_saved >= 3600:
                lt_str = f"{lifetime_saved / 3600:.1f} hours"
            elif lifetime_saved >= 60:
                lt_str = f"{lifetime_saved / 60:.0f} minutes"
            else:
                lt_str = f"{lifetime_saved:.0f} seconds"
            s_str = f"{sessions} session{'s' if sessions != 1 else ''}"
            since = datetime.fromisoformat(first_use).strftime("%b %d, %Y")
            print(f"All time: {lt_str} saved across {s_str} (since {since})", file=sys.stderr)
    except Exception:
        pass

def run_agent(
    agent_id: str,
    command: list[str],
    verbose: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    status_bar: bool = True,
    clear_on_start: bool = True,
    claim_key: str = "ctrl+\\",
    agent_label: str | None = None,
    scroll_region: bool = True,
) -> int:
    """Run a command with multiplexed input from stdin and dictare SSE.

    Connects to the engine's HTTP server via SSE to receive OpenVIP messages.
    The SSE connection itself registers the agent with the engine.

    Args:
        agent_id: Agent identifier (e.g., 'claude').
        command: Command and arguments to run.
        verbose: Enable verbose agent logging and full text in session file.
        base_url: Engine HTTP server base URL.
        status_bar: Show persistent status bar on last terminal row.
        clear_on_start: Clear terminal before launching child process.
        claim_key: Key combo to claim this agent (e.g. "ctrl+\\", "ctrl+]").

    Returns:
        Exit code of the process.
    """
    # --- Pre-flight checks (before touching the terminal) ---
    # 1. Engine must be reachable
    # 2. Agent name must not be taken
    from openvip import Client as _OVClient

    try:
        _pf_client = _OVClient(base_url, timeout=3)
        _pf_status = _pf_client.get_status()
    except Exception:
        print(f"[dictare] Error: engine is not running at {base_url}", file=sys.stderr)
        return 1

    if _pf_status.connected_agents and agent_id in _pf_status.connected_agents:
        print(
            f"[dictare] Error: agent '{agent_id}' is already connected",
            file=sys.stderr,
        )
        return 1

    # --- Pre-flight OK — proceed with session setup ---
    # Parse claim key once at startup
    claim_raw, claim_csi_u = _parse_claim_key(claim_key)

    # Create session log
    session_path = _get_session_log_path(agent_id)
    _write_session_start(session_path, agent_id, command, base_url)

    # Set up agent log file (standard logging)
    _agent_log_handler = setup_logging(
        log_path=Path.home() / ".local" / "share" / "dictare" / "logs" / f"agent.{agent_id}.jsonl",
        level=logging.DEBUG if verbose else logging.INFO,
        version=__version__,
        source=f"agent.{agent_id}",
    )

    # Log banner info (instead of printing to stderr)
    logger.info("agent_start", extra={
        "agent_id": agent_id,
        "server": base_url,
        "session": str(session_path),
        "command": " ".join(command),
        "scroll_region": scroll_region,
    })

    # Load redact rules (list of [find, replace] byte pairs)
    from dictare.config import load_config

    _redact_rules: list[tuple[bytes, bytes]] = []
    try:
        _cfg = load_config()
        for rule in _cfg.redact:
            if len(rule) == 2:
                _redact_rules.append((rule[0].encode(), rule[1].encode()))
    except Exception:
        pass

    # Save original terminal settings
    old_settings = None
    if sys.stdin.isatty():
        old_settings = termios.tcgetattr(sys.stdin.fileno())

    rows, cols = _get_winsize()
    sbar = StatusBar(agent_id, agent_label=agent_label, cwd=Path.cwd(), use_scroll_region=scroll_region) if status_bar else None

    # Auto-detection: if the child sends its own DECSTBM set sequences,
    # we must disable our scroll region to avoid conflicts.
    _sr_active = scroll_region  # mutable — can be disabled at runtime

    def _disable_scroll_region() -> None:
        nonlocal _sr_active
        if not _sr_active:
            return
        _sr_active = False
        # Remove our scroll region and let the child manage its own
        if sbar:
            sbar._use_scroll_region = False
            sbar._region_esc = b""
        # Reset scroll region to full screen
        sys.stdout.buffer.write(b"\x1b[r")
        sys.stdout.buffer.flush()
        logger.info("scroll_region_auto_disabled", extra={
            "reason": "child uses own DECSTBM sequences",
        })

    def on_output(data: bytes) -> None:
        for find, replace in _redact_rules:
            data = data.replace(find, replace)

        # Auto-detect: child sets its own scroll region → disable ours
        if _sr_active and _DECSTBM_SET_RE.search(data):
            _disable_scroll_region()

        # Rewrite bare DECSTBM reset so child can't destroy our scroll region.
        if sbar and _sr_active and _DECSTBM_RESET in data:
            safe_region = f"\x1b[1;{sbar._rows - 1}r".encode()
            data = data.replace(_DECSTBM_RESET, safe_region)
        os.write(sys.stdout.fileno(), data)
        if sbar and _sr_active:
            sbar.after_child_output()
        if sbar and _sr_active and (_SCREEN_CLEAR in data or _ERASE_BELOW in data):
            sbar.request_redraw()
        if sbar and not _sr_active:
            sbar.mark_child_output()

    def on_resize(r: int, c: int) -> None:
        if sbar:
            sbar.on_resize(r, c)

    session = PTYSession(
        command, rows, cols,
        on_output=on_output,
        on_resize=on_resize,
        reserve_rows=1 if sbar and scroll_region else 0,
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

        # Enable terminal focus reporting (xterm extension)
        sys.stdout.buffer.write(_FOCUS_ENABLE)
        sys.stdout.buffer.flush()

        # Assume focused at launch — the terminal we just opened almost certainly
        # has focus.  The ?1004h API only sends events (gained/lost), it cannot
        # answer "do you have focus right now?", so we must assume.
        _report_focus(agent_id, base_url, True)

        stop_event = threading.Event()

        # Create thread-safe queue for serialized writes to PTY
        write_queue: queue.Queue = queue.Queue()

        # Create keystroke counter for session statistics
        keystroke_counter = KeystrokeCounter()

        master_fd = session.master_fd

        # Start producer threads (read from stdin/SSE, put in queue)
        stdin_thread = threading.Thread(
            target=_read_from_stdin,
            args=(write_queue, stop_event, keystroke_counter, agent_id, base_url, session_path),
            kwargs={"claim_key_raw": claim_raw, "claim_key_csi_u": claim_csi_u},
            daemon=True,
        )
        # SSE-based IPC: connect to engine HTTP server
        sse_thread = threading.Thread(
            target=_read_from_sse,
            args=(agent_id, base_url, write_queue, stop_event, session_path, keystroke_counter, verbose),
            kwargs={"on_status": sbar.update if sbar else None},
            daemon=True,
        )
        # Start consumer thread (read from queue, write to PTY)
        writer_thread = threading.Thread(
            target=_write_to_pty,
            args=(master_fd, write_queue, stop_event, session_path, keystroke_counter, verbose),
            daemon=True,
        )
        # Stream engine status via SSE (status bar: listening/off/standby)
        if sbar:
            status_thread = threading.Thread(
                target=_stream_active_agent,
                args=(agent_id, base_url, stop_event, sbar.update),
                daemon=True,
            )

        stdin_thread.start()
        sse_thread.start()
        writer_thread.start()
        if sbar:
            status_thread.start()

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
        # Disable focus reporting and signal unfocused before cleanup
        try:
            sys.stdout.buffer.write(_FOCUS_DISABLE)
            sys.stdout.buffer.flush()
        except OSError:
            pass
        _report_focus(agent_id, base_url, False)

        # Reset scroll region before restoring terminal
        if sbar:
            sbar.cleanup()

        # Restore terminal settings
        if old_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

        session.cleanup()

        _print_session_summary(base_url)

        # Clean up agent log handler
        if _agent_log_handler:
            logging.getLogger("dictare").removeHandler(_agent_log_handler)
            _agent_log_handler.close()
