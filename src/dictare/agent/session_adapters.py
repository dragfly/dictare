"""Per-agent session adapters — phase 2 of named session continuity.

Each adapter knows how one agent CLI expresses "start a session I can find
again" and "resume exactly that session". Adapters are keyed on the command
binary (``claude``, ``codex``, ...), not on the profile name, so custom
profiles get the right adapter for free.

Everything here is best-effort by contract: an adapter that cannot produce an
exact binding returns None and the caller falls back to the profile's plain
``continue_args`` (phase 1 behavior). The registry stays a pointer; each
agent's own session store is canonical.

Verified against installed CLIs on 2026-07-03: claude 2.1.187, codex 0.142.5,
gemini 0.46.0, pi 0.57.1, aider 0.86.2. These CLIs move fast — adapters must
degrade, never crash, when flags change.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dictare.agent.session_registry import REGISTRY_DIR, _encode_cwd

logger = logging.getLogger(__name__)


@dataclass
class LaunchPlan:
    """How to start a new bindable session."""

    extra_args: list[str] = field(default_factory=list)
    binding: dict[str, str] = field(default_factory=dict)


class SessionAdapter:
    """Base adapter: no binding capability (phase 1 behavior)."""

    def new_session(self, cwd: str, name: str) -> LaunchPlan:
        """Args to inject when STARTING a session, plus fields to persist."""
        return LaunchPlan()

    def resume_args(self, entry: dict[str, Any]) -> list[str] | None:
        """Args that resume the exact bound session, or None if unbound."""
        return None

    def discover_binding(self, cwd: str, launched_after: float) -> dict[str, str]:
        """Best-effort post-exit discovery of the session identity."""
        return {}


def _first_line_json(path: Path) -> dict[str, Any]:
    """Parse the first jsonl line of a session file ({} on any problem)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.loads(f.readline())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _newest_session_file(
    root: Path, pattern: str, min_mtime: float, cwd: str, get_cwd: Any
) -> Path | None:
    """Newest session file for *cwd* under *root* modified after *min_mtime*.

    *get_cwd* extracts the recorded cwd from the file's first-line header, so
    concurrent sessions in other folders can never be mis-bound.
    """
    try:
        candidates = [
            p
            for p in root.rglob(pattern)
            if p.is_file() and p.stat().st_mtime >= min_mtime
        ]
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for path in candidates:
        if get_cwd(_first_line_json(path)) == cwd:
            return path
    return None


class ClaudeAdapter(SessionAdapter):
    """claude: dictare assigns the session id and names the session natively.

    ``--resume <uuid>`` reuses the same id (no ``--fork-session``), so the
    binding stays stable across resumes.
    """

    def new_session(self, cwd: str, name: str) -> LaunchPlan:
        session_id = str(uuid.uuid4())
        return LaunchPlan(
            extra_args=["--session-id", session_id, "--name", name],
            binding={"session_id": session_id},
        )

    def resume_args(self, entry: dict[str, Any]) -> list[str] | None:
        session_id = entry.get("session_id")
        return ["--resume", str(session_id)] if session_id else None


class GeminiAdapter(SessionAdapter):
    """gemini: dictare assigns the session id; resume by uuid."""

    def new_session(self, cwd: str, name: str) -> LaunchPlan:
        session_id = str(uuid.uuid4())
        return LaunchPlan(
            extra_args=["--session-id", session_id],
            binding={"session_id": session_id},
        )

    def resume_args(self, entry: dict[str, Any]) -> list[str] | None:
        session_id = entry.get("session_id")
        return ["--resume", str(session_id)] if session_id else None


class AiderAdapter(SessionAdapter):
    """aider: no native session model — bind a dictare-owned history file.

    Passing the same ``--chat-history-file`` with ``--restore-chat-history``
    both creates and resumes the session, and gives aider multiple named
    sessions per folder (which it lacks natively).
    """

    def _history_path(self, cwd: str, name: str) -> Path:
        return REGISTRY_DIR / f"{_encode_cwd(cwd)}.sessions" / f"aider-{name}.md"

    def new_session(self, cwd: str, name: str) -> LaunchPlan:
        path = self._history_path(cwd, name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.debug("Cannot create aider session dir", exc_info=True)
            return LaunchPlan()
        return LaunchPlan(
            extra_args=[
                "--chat-history-file",
                str(path),
                "--restore-chat-history",
            ],
            binding={"session_path": str(path)},
        )

    def resume_args(self, entry: dict[str, Any]) -> list[str] | None:
        session_path = entry.get("session_path")
        if not session_path:
            return None
        return [
            "--chat-history-file",
            str(session_path),
            "--restore-chat-history",
        ]


class PiAdapter(SessionAdapter):
    """pi: sessions are per-folder jsonl files — bind the file discovered at exit."""

    SESSIONS_ROOT = Path.home() / ".pi" / "agent" / "sessions"

    def resume_args(self, entry: dict[str, Any]) -> list[str] | None:
        session_path = entry.get("session_path")
        if session_path and Path(str(session_path)).is_file():
            return ["--session", str(session_path)]
        return None

    def discover_binding(self, cwd: str, launched_after: float) -> dict[str, str]:
        newest = _newest_session_file(
            self.SESSIONS_ROOT,
            "*.jsonl",
            launched_after,
            cwd,
            lambda header: header.get("cwd"),
        )
        return {"session_path": str(newest)} if newest else {}


class CodexAdapter(SessionAdapter):
    """codex: cannot assign an id — discover it from the rollout file at exit.

    Rollout files are ``rollout-<timestamp>-<uuid>.jsonl`` under
    ``~/.codex/sessions/YYYY/MM/DD/``. Resume is the ``resume`` subcommand.
    """

    SESSIONS_ROOT = Path.home() / ".codex" / "sessions"
    _ROLLOUT_RE = re.compile(
        r"rollout-.*-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
    )

    def resume_args(self, entry: dict[str, Any]) -> list[str] | None:
        session_id = entry.get("session_id")
        return ["resume", str(session_id)] if session_id else None

    def discover_binding(self, cwd: str, launched_after: float) -> dict[str, str]:
        newest = _newest_session_file(
            self.SESSIONS_ROOT,
            "rollout-*.jsonl",
            launched_after,
            cwd,
            lambda header: (header.get("payload") or {}).get("cwd"),
        )
        if not newest:
            return {}
        # Prefer the id recorded in the header; fall back to the filename.
        header = _first_line_json(newest)
        session_id = (header.get("payload") or {}).get("session_id")
        if session_id:
            return {"session_id": str(session_id)}
        match = self._ROLLOUT_RE.search(newest.name)
        return {"session_id": match.group(1)} if match else {}


_ADAPTERS: dict[str, SessionAdapter] = {
    "claude": ClaudeAdapter(),
    "gemini": GeminiAdapter(),
    "aider": AiderAdapter(),
    "pi": PiAdapter(),
    "codex": CodexAdapter(),
}


def get_adapter(binary: str) -> SessionAdapter | None:
    """Return the adapter for a command binary basename, or None."""
    return _ADAPTERS.get(Path(binary).name)
