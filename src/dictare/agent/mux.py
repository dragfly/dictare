"""Agent multiplexer - run commands with merged stdin and dictare input."""

from __future__ import annotations

import json
import logging
import os
import platform
import queue
import re
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
from dictare.logging.setup import setup_logging
from dictare.pipeline.base import PipelineAction
from dictare.pipeline.executors import InputExecutor
from dictare.utils.stats import update_keystrokes

logger = logging.getLogger(__name__)

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
_CTRL_BACKSLASH_SEQS = [b"\x1b[92;5u", b"\x1b[27;5;92~"]

# Terminal focus reporting escape sequences (xterm extension, widely supported)
_FOCUS_ENABLE = b"\x1b[?1004h"
_FOCUS_DISABLE = b"\x1b[?1004l"
_FOCUS_IN = b"\x1b[I"
_FOCUS_OUT = b"\x1b[O"

_MODIFIER_VALUES = range(1, 257)
_KITTY_EVENT_TYPES = (1, 2, 3)

_EVDEV_TO_KITTY_CODE = {
    "KEY_ESC": 27,
    "KEY_ESCAPE": 27,
    "KEY_ENTER": 13,
    "KEY_TAB": 9,
    "KEY_BACKSPACE": 127,
    "KEY_CAPSLOCK": 57358,
    "KEY_SCROLLLOCK": 57359,
    "KEY_NUMLOCK": 57360,
    "KEY_SYSRQ": 57361,
    "KEY_PRINTSCREEN": 57361,
    "KEY_PAUSE": 57362,
    "KEY_MENU": 57363,
    "KEY_KP0": 57399,
    "KEY_KP1": 57400,
    "KEY_KP2": 57401,
    "KEY_KP3": 57402,
    "KEY_KP4": 57403,
    "KEY_KP5": 57404,
    "KEY_KP6": 57405,
    "KEY_KP7": 57406,
    "KEY_KP8": 57407,
    "KEY_KP9": 57408,
    "KEY_KPDOT": 57409,
    "KEY_KPSLASH": 57410,
    "KEY_KPASTERISK": 57411,
    "KEY_KPMINUS": 57412,
    "KEY_KPPLUS": 57413,
    "KEY_KPENTER": 57414,
    "KEY_KPEQUAL": 57415,
    "KEY_LEFTSHIFT": 57441,
    "KEY_LEFTCTRL": 57442,
    "KEY_LEFTALT": 57443,
    "KEY_LEFTMETA": 57444,
    "KEY_LEFTSUPER": 57444,
    "KEY_RIGHTSHIFT": 57447,
    "KEY_RIGHTCTRL": 57448,
    "KEY_RIGHTALT": 57449,
    "KEY_RIGHTMETA": 57450,
    "KEY_RIGHTSUPER": 57450,
    "KEY_PLAY": 57428,
    "KEY_PAUSECD": 57429,
    "KEY_PLAYPAUSE": 57430,
    "KEY_STOPCD": 57432,
    "KEY_FASTFORWARD": 57433,
    "KEY_REWIND": 57434,
    "KEY_NEXTSONG": 57435,
    "KEY_PREVIOUSSONG": 57436,
    "KEY_RECORD": 57437,
    "KEY_VOLUMEDOWN": 57438,
    "KEY_VOLUMEUP": 57439,
    "KEY_MUTE": 57440,
}

_LEGACY_TILDE_CODES = {
    "KEY_INSERT": 2,
    "KEY_DELETE": 3,
    "KEY_PAGEUP": 5,
    "KEY_PAGEDOWN": 6,
    "KEY_HOME": 7,
    "KEY_END": 8,
    "KEY_F1": 11,
    "KEY_F2": 12,
    "KEY_F3": 13,
    "KEY_F4": 14,
    "KEY_F5": 15,
    "KEY_F6": 17,
    "KEY_F7": 18,
    "KEY_F8": 19,
    "KEY_F9": 20,
    "KEY_F10": 21,
    "KEY_F11": 23,
    "KEY_F12": 24,
    "KEY_MENU": 29,
}

_LEGACY_LETTER_CODES = {
    "KEY_UP": "A",
    "KEY_DOWN": "B",
    "KEY_RIGHT": "C",
    "KEY_LEFT": "D",
    "KEY_BEGIN": "E",
    "KEY_END": "F",
    "KEY_HOME": "H",
    "KEY_F1": "P",
    "KEY_F2": "Q",
    "KEY_F3": "R",
    "KEY_F4": "S",
}

_SS3_CODES = {
    "KEY_UP": "A",
    "KEY_DOWN": "B",
    "KEY_RIGHT": "C",
    "KEY_LEFT": "D",
    "KEY_HOME": "H",
    "KEY_END": "F",
    "KEY_F1": "P",
    "KEY_F2": "Q",
    "KEY_F3": "R",
    "KEY_F4": "S",
}

# PTY delivery timing.
#
# Text and submit are logically separate operations. Keep the bytes separate in
# the PTY too: first write text, drain, then write Enter. Some terminal TUIs are
# sensitive to receiving the submit byte immediately after a large text write,
# so the text→submit gap is intentionally visible and logged.
_VISUAL_NEWLINE_DELAY_SECONDS = 0.01
_SUBMIT_ONLY_DELAY_SECONDS = 0.01
_SUBMIT_AFTER_TEXT_DELAY_SECONDS = 0.075

def _parse_claim_key(key_str: str) -> tuple[bytes, list[bytes]]:
    """Parse a claim key string into (raw_byte, escape_sequences).

    Supports ``ctrl+<char>`` format.  For any ``ctrl+X``, terminals may
    send one of three encodings depending on the active keyboard mode:

    - Raw mode byte: ``ord(X) & 0x1F``
    - Kitty CSI u:   ``ESC[{ord(X)};5u``
    - xterm modifyOtherKeys: ``ESC[27;5;{ord(X)}~``

    Args:
        key_str: Key specification, e.g. ``"ctrl+\\\\"`` or ``"ctrl+]"``.

    Returns:
        Tuple of (raw_byte, list_of_escape_sequences).

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
    escape_seqs = [
        f"\x1b[{ord(char)};5u".encode(),       # Kitty CSI u
        f"\x1b[27;5;{ord(char)}~".encode(),     # xterm modifyOtherKeys
    ]
    return raw, escape_seqs

def _strip_claim_key(data: bytes, raw: bytes, escape_seqs: list[bytes]) -> tuple[bytes, bool]:
    """Remove all claim key variants from *data*.

    Returns (cleaned_data, found) where *found* is True if any
    claim key sequence was present.
    """
    found = False
    for seq in escape_seqs:
        if seq in data:
            data = data.replace(seq, b"")
            found = True
    if raw in data:
        data = data.replace(raw, b"")
        found = True
    return data, found

def _strip_terminal_sequences(data: bytes, sequences: list[bytes]) -> tuple[bytes, bool]:
    """Remove exact terminal escape sequences from *data*."""
    found = False
    for seq in sequences:
        if seq and seq in data:
            data = data.replace(seq, b"")
            found = True
    return data, found

def _kitty_csi_u_sequences(code: int) -> list[bytes]:
    """Return kitty/CSI-u encodings for one functional key code."""
    sequences = [f"\x1b[{code}u".encode()]
    for modifier in _MODIFIER_VALUES:
        sequences.append(f"\x1b[{code};{modifier}u".encode())
        for event_type in _KITTY_EVENT_TYPES:
            sequences.append(f"\x1b[{code};{modifier}:{event_type}u".encode())
    return sequences

def _legacy_tilde_sequences(code: int) -> list[bytes]:
    """Return xterm-style ``CSI number ~`` encodings for a functional key."""
    sequences = [f"\x1b[{code}~".encode()]
    for modifier in _MODIFIER_VALUES:
        sequences.append(f"\x1b[{code};{modifier}~".encode())
    return sequences

def _legacy_letter_sequences(letter: str) -> list[bytes]:
    """Return xterm/kitty legacy ``CSI 1;modifier <letter>`` encodings."""
    sequences = [f"\x1b[{letter}".encode(), f"\x1b[1{letter}".encode()]
    for modifier in _MODIFIER_VALUES:
        sequences.append(f"\x1b[1;{modifier}{letter}".encode())
    return sequences

def _normalize_evdev_key_name(key_name: str | None) -> str:
    """Normalize configured hotkey names to evdev-style names."""
    if not key_name:
        return ""
    normalized = key_name.strip().upper().replace("-", "_")
    if not normalized:
        return ""
    if re.fullmatch(r"F\d{1,2}", normalized):
        return f"KEY_{normalized}"
    if not normalized.startswith("KEY_"):
        return f"KEY_{normalized}"
    return normalized

def _terminal_sequences_for_evdev_key(key_name: str | None) -> list[bytes]:
    """Return terminal sequences that can represent a configured global hotkey.

    Dictare observes the global hotkey through platform input APIs, but the same
    physical key can still arrive on stdin when the agent terminal is in raw
    mode.  Keep this scoped to the configured key instead of stripping arbitrary
    CSI-u input.
    """
    normalized = _normalize_evdev_key_name(key_name)
    if not normalized:
        return []

    sequences: list[bytes] = []
    match = re.fullmatch(r"KEY_F(\d{1,2})", normalized)
    if match:
        number = int(match.group(1))
        if 13 <= number <= 35:
            sequences.extend(_kitty_csi_u_sequences(57376 + number - 13))

    kitty_code = _EVDEV_TO_KITTY_CODE.get(normalized)
    if kitty_code is not None:
        sequences.extend(_kitty_csi_u_sequences(kitty_code))

    legacy_tilde = _LEGACY_TILDE_CODES.get(normalized)
    if legacy_tilde is not None:
        sequences.extend(_legacy_tilde_sequences(legacy_tilde))

    legacy_letter = _LEGACY_LETTER_CODES.get(normalized)
    if legacy_letter is not None:
        sequences.extend(_legacy_letter_sequences(legacy_letter))

    ss3_letter = _SS3_CODES.get(normalized)
    if ss3_letter is not None:
        sequences.append(f"\x1bO{ss3_letter}".encode())

    return sorted(set(sequences), key=len, reverse=True)

# Backward-compatible alias used by existing tests
def _strip_ctrl_backslash(data: bytes) -> tuple[bytes, bool]:
    """Remove Ctrl+\\\\ from *data* (backward-compatible wrapper)."""
    return _strip_claim_key(data, _CTRL_BACKSLASH, _CTRL_BACKSLASH_SEQS)

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
    claim_key_seqs: list[bytes] | None = None,
    info_key_raw: bytes | None = None,
    info_key_seqs: list[bytes] | None = None,
    on_info: Callable[[], None] | None = None,
    global_hotkey_key: str | None = None,
    global_hotkey_seqs: list[bytes] | None = None,
) -> None:
    """Read from keyboard in raw mode and put data in queue.

    When *agent_id* is set, the claim key is intercepted and sends
    ``output.set_agent:<agent_id>`` to the engine, making this
    terminal the active voice target.  The keystroke is consumed
    and never forwarded to the child process.

    When *info_key_raw* and *on_info* are set, the info key is
    intercepted and *on_info* is called (agent info notification).

    When *global_hotkey_seqs* is set, terminal escape sequences for the
    configured global hotkey are consumed so they do not leak into the child
    process after the platform hotkey listener handles the event.

    Supports raw-mode byte, kitty CSI u, and xterm modifyOtherKeys.
    """
    if claim_key_seqs is None:
        claim_key_seqs = _CTRL_BACKSLASH_SEQS
    if global_hotkey_seqs is None:
        global_hotkey_seqs = []
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
                    data, found = _strip_claim_key(data, claim_key_raw, claim_key_seqs)
                    if found:
                        if session_path:
                            _log_event(session_path, "claim_key", {
                                "agent_id": agent_id,
                                "base_url": base_url,
                            })
                        _claim_agent(agent_id, base_url)
                        if not data:
                            continue

                # Intercept info key to show agent info notification
                if on_info and info_key_raw:
                    data, found = _strip_claim_key(data, info_key_raw, info_key_seqs or [])
                    if found:
                        if session_path:
                            _log_event(session_path, "info_key", {"agent_id": agent_id})
                        on_info()
                        if not data:
                            continue

                # Consume terminal-side representation of the configured global hotkey
                if global_hotkey_seqs:
                    data, found = _strip_terminal_sequences(data, global_hotkey_seqs)
                    if found:
                        if session_path:
                            _log_event(session_path, "global_hotkey", {
                                "agent_id": agent_id,
                                "key": global_hotkey_key,
                            })
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

def _abbreviate_home(path: str) -> str:
    """Replace the user's home prefix with ``~`` (no-op if path is outside home)."""
    home = str(Path.home())
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def _format_agent_info(
    agent_id: str,
    platform_status: dict,
    cwd: str | None = None,
    danger_args: list[str] | None = None,
) -> str:
    """Build the notification body: agent name, voice state, current target,
    cwd, and a live-dangerously marker when permission-bypass args were
    injected (the start-time terminal warning is wiped by TUI agents, so the
    on-demand notification is where the mode stays visible)."""
    from dictare.status import resolve_display_state

    state, _style = resolve_display_state(platform_status, agent_id)
    current = platform_status.get("output", {}).get("current_agent")
    if current == agent_id:
        header = f"{agent_id} — {state}"
    elif current:
        header = f"{agent_id} — {state} (current: {current})"
    else:
        header = f"{agent_id} — {state} (no voice target)"
    lines = [header]
    if cwd:
        lines.append(_abbreviate_home(cwd))
    if danger_args:
        lines.append(f"⚠ live-dangerously: {' '.join(danger_args)}")
    return "\n".join(lines)

def _notify(title: str, message: str) -> None:
    """Show a system notification (best-effort, never raises)."""
    import subprocess

    try:
        if sys.platform == "darwin":
            esc_msg = message.replace("\\", "\\\\").replace('"', '\\"')
            esc_title = title.replace("\\", "\\\\").replace('"', '\\"')
            script = f'display notification "{esc_msg}" with title "{esc_title}"'
            subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
        else:
            subprocess.run(["notify-send", title, message], timeout=5, capture_output=True)
    except Exception:
        pass

def _show_agent_info(
    agent_id: str, base_url: str, danger_args: list[str] | None = None
) -> None:
    """Fetch engine status and show it as a system notification (fire-and-forget)."""
    cwd = os.getcwd()

    def _do() -> None:
        try:
            from openvip import Client

            status = Client(base_url, timeout=3).get_status()
            body = _format_agent_info(
                agent_id, status.platform or {}, cwd=cwd, danger_args=danger_args
            )
        except Exception:
            body = f"{agent_id} — engine unreachable\n{_abbreviate_home(cwd)}"
        _notify("Dictare", body)

    threading.Thread(target=_do, daemon=True).start()

def _read_from_sse(
    agent_id: str,
    base_url: str,
    write_queue: queue.Queue,
    stop_event: threading.Event,
    session_path: Path | None = None,
    keystroke_counter: KeystrokeCounter | None = None,
    verbose: bool = False,
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

            # Process through executor pipeline (needs raw dict for x_input access)
            msg_dict = msg.to_dict()
            x_input = msg_dict.get("x_input")
            x_input_ops = x_input.get("ops") or [] if isinstance(x_input, dict) else []
            submit_requested = "submit" in x_input_ops
            newline_requested = "newline" in x_input_ops

            # Set openvip metadata for the executor's write_fn
            _openvip_meta.clear()
            _openvip_meta["openvip_id"] = msg_id
            _openvip_meta["openvip_ts"] = msg_ts
            _openvip_meta["x_input_ops"] = list(x_input_ops)
            if isinstance(x_input, dict):
                _openvip_meta["x_input_source"] = x_input.get("source")
                _openvip_meta["submit_trigger"] = x_input.get("trigger")

            msg_count += 1
            if session_path:
                text = msg.text or ""
                _log_event(session_path, "msg_read", {
                    "seq": msg_count,
                    "text": text if verbose else (text[:20] + "[...]" if len(text) > 20 else text),
                    "chars": len(text),
                    "openvip_id": msg_id,
                    "x_input_ops": list(x_input_ops),
                    "submit_requested": submit_requested,
                    "newline_requested": newline_requested,
                    "x_input_source": _openvip_meta.get("x_input_source"),
                    "submit_trigger": _openvip_meta.get("submit_trigger"),
                    "keystrokes": keystroke_counter.count if keystroke_counter else 0,
                })

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
                original_text = text
                submit = bool(data.get("submit"))
                x_input_ops = data.get("x_input_ops") or []
                text_bytes_written = 0
                visual_newline_bytes_written = 0
                submit_bytes_written = 0

                if session_path:
                    _log_event(session_path, "msg_write_started", {
                        "seq": msg_count,
                        "chars": len(original_text),
                        "submit": submit,
                        "x_input_ops": x_input_ops,
                        "x_input_source": data.get("x_input_source"),
                        "submit_trigger": data.get("submit_trigger"),
                        "openvip_id": data.get("openvip_id"),
                        "openvip_ts": data.get("openvip_ts"),
                        "keystrokes": keystroke_counter.count if keystroke_counter else 0,
                    })

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
                        text_bytes_written = _write_all(master_fd, text_bytes)
                        termios.tcdrain(master_fd)
                        if session_path:
                            _log_event(session_path, "msg_text_written", {
                                "seq": msg_count,
                                "bytes": text_bytes_written,
                                "openvip_id": data.get("openvip_id"),
                            })

                    # Alt+Enter for visual newline (contains ESC — must be separate).
                    # 10ms grace period so the slave reads text before ESC arrives.
                    if has_visual_newline:
                        stop_event.wait(_VISUAL_NEWLINE_DELAY_SECONDS)
                        visual_newline_bytes_written = _write_all(master_fd, alt_enter)
                        termios.tcdrain(master_fd)
                        if session_path:
                            _log_event(session_path, "msg_visual_newline_written", {
                                "seq": msg_count,
                                "bytes": visual_newline_bytes_written,
                                "delay_s": _VISUAL_NEWLINE_DELAY_SECONDS,
                                "openvip_id": data.get("openvip_id"),
                            })

                # Submit enter (plain CR — no ESC, safe to write anytime)
                if submit:
                    delay_s = (
                        _SUBMIT_AFTER_TEXT_DELAY_SECONDS
                        if text_bytes_written or visual_newline_bytes_written
                        else _SUBMIT_ONLY_DELAY_SECONDS
                    )
                    stop_event.wait(delay_s)
                    submit_bytes_written = _write_all(master_fd, enter_key)
                    termios.tcdrain(master_fd)
                    if session_path:
                        _log_event(session_path, "msg_submit_written", {
                            "seq": msg_count,
                            "bytes": submit_bytes_written,
                            "delay_s": delay_s,
                            "openvip_id": data.get("openvip_id"),
                            "submit_trigger": data.get("submit_trigger"),
                        })

                # Log message AFTER successful write AND drain
                if session_path:
                    text = original_text
                    bytes_written = (
                        text_bytes_written
                        + visual_newline_bytes_written
                        + submit_bytes_written
                    )
                    _log_event(session_path, "msg_sent", {
                        "seq": msg_count,
                        "text": text if verbose else (text[:20] + "[...]" if len(text) > 20 else text),
                        "chars": len(text),
                        "bytes": bytes_written,
                        "text_bytes": text_bytes_written,
                        "visual_newline_bytes": visual_newline_bytes_written,
                        "submit_bytes": submit_bytes_written,
                        "submit": submit,
                        "x_input_ops": x_input_ops,
                        "x_input_source": data.get("x_input_source"),
                        "submit_trigger": data.get("submit_trigger"),
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
    clear_on_start: bool = True,
    claim_key: str = "ctrl+\\",
    info_key: str = "ctrl+]",
    global_hotkey_key: str | None = None,
    live_dangerously_args: list[str] | None = None,
) -> int:
    """Run a command with multiplexed input from stdin and dictare SSE.

    Connects to the engine's HTTP server via SSE to receive OpenVIP messages.
    The SSE connection itself registers the agent with the engine.

    Args:
        agent_id: Agent identifier (e.g., 'claude').
        command: Command and arguments to run.
        verbose: Enable verbose agent logging and full text in session file.
        base_url: Engine HTTP server base URL.
        clear_on_start: Clear terminal before launching child process.
        claim_key: Key combo to claim this agent (e.g. "ctrl+\\", "ctrl+]").
        info_key: Key combo to show agent info as a system notification
            (empty string disables it).
        global_hotkey_key: Evdev-style global hotkey key name to consume from
            terminal stdin when the terminal also reports the physical key.
        live_dangerously_args: Permission-bypass args that were injected into
            the command, shown in the info notification when set.

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
    # Parse claim and info keys once at startup
    claim_raw, claim_seqs = _parse_claim_key(claim_key)
    global_hotkey_seqs = _terminal_sequences_for_evdev_key(global_hotkey_key)
    info_raw: bytes | None = None
    info_seqs: list[bytes] = []
    if info_key:
        info_raw, info_seqs = _parse_claim_key(info_key)
        if info_raw == claim_raw:
            logger.warning("info_key equals claim_key — info notification disabled")
            info_raw = None

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

    def on_output(data: bytes) -> None:
        for find, replace in _redact_rules:
            data = data.replace(find, replace)
        os.write(sys.stdout.fileno(), data)

    session = PTYSession(command, rows, cols, on_output=on_output)

    try:
        # Clear terminal for clean start (before launching child process
        # so that any immediate errors from the child are visible)
        if clear_on_start:
            sys.stdout.buffer.write(b"\x1b[2J\x1b[H")
            sys.stdout.buffer.flush()

        session.start()

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
            kwargs={
                "claim_key_raw": claim_raw,
                "claim_key_seqs": claim_seqs,
                "info_key_raw": info_raw,
                "info_key_seqs": info_seqs,
                "global_hotkey_key": global_hotkey_key,
                "global_hotkey_seqs": global_hotkey_seqs,
                "on_info": (
                    (lambda: _show_agent_info(agent_id, base_url, live_dangerously_args))
                    if info_raw
                    else None
                ),
            },
            daemon=True,
        )
        # SSE-based IPC: connect to engine HTTP server
        sse_thread = threading.Thread(
            target=_read_from_sse,
            args=(agent_id, base_url, write_queue, stop_event, session_path, keystroke_counter, verbose),
            daemon=True,
        )
        # Start consumer thread (read from queue, write to PTY)
        writer_thread = threading.Thread(
            target=_write_to_pty,
            args=(master_fd, write_queue, stop_event, session_path, keystroke_counter, verbose),
            daemon=True,
        )
        stdin_thread.start()
        sse_thread.start()
        writer_thread.start()

        exit_code = session.run_output_loop()
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

        # Restore terminal settings
        if old_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

        session.cleanup()

        _print_session_summary(base_url)

        # Clean up agent log handler
        if _agent_log_handler:
            logging.getLogger("dictare").removeHandler(_agent_log_handler)
            _agent_log_handler.close()
