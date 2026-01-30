"""Agent auto-discovery via filesystem watcher.

Monitors the socket directory for agent .sock files and notifies
when agents appear or disappear.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from voxtype.utils.platform import get_socket_dir

# Internal sockets to exclude from agent discovery
INTERNAL_SOCKETS = {"daemon.sock", "control.sock"}


@dataclass
class Agent:
    """Discovered agent info."""

    id: str
    socket_path: Path
    created_at: float  # mtime of socket file


@dataclass
class AgentWatcher:
    """Watches socket directory for agent changes.

    Usage:
        watcher = AgentWatcher(
            on_agent_added=lambda a: print(f"New agent: {a.id}"),
            on_agent_removed=lambda a: print(f"Agent gone: {a.id}"),
        )
        watcher.start()
        # ... later ...
        watcher.stop()
    """

    on_agent_added: Callable[[Agent], None] | None = None
    on_agent_removed: Callable[[Agent], None] | None = None

    _agents: dict[str, Agent] = field(default_factory=dict, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _observer: BaseObserver | None = field(default=None, init=False)
    _socket_dir: Path | None = field(default=None, init=False)

    @property
    def agents(self) -> list[Agent]:
        """Get list of discovered agents, sorted by creation time."""
        with self._lock:
            return sorted(self._agents.values(), key=lambda a: a.created_at)

    @property
    def agent_ids(self) -> list[str]:
        """Get list of agent IDs, sorted by creation time."""
        return [a.id for a in self.agents]

    def start(self) -> None:
        """Start watching for agents."""
        self._socket_dir = get_socket_dir()

        # Initial discovery (no callbacks - caller reads agent_ids after start)
        self._discover_existing_agents(emit_callbacks=False)

        # Start filesystem watcher (callbacks enabled for runtime changes)
        handler = _AgentEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._socket_dir), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        """Stop watching."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None

    def _discover_existing_agents(self, emit_callbacks: bool = True) -> None:
        """Discover agents that already exist at startup."""
        if not self._socket_dir:
            return

        for sock_file in self._socket_dir.glob("*.sock"):
            self._handle_socket_created(sock_file, emit_callback=emit_callbacks)

    def _handle_socket_created(self, path: Path, *, emit_callback: bool = True) -> None:
        """Handle a socket file being created."""
        if path.name in INTERNAL_SOCKETS:
            return

        agent_id = path.stem

        # Check if socket is alive (has a listener)
        if not _is_socket_alive(path):
            # Stale socket, remove it
            try:
                path.unlink()
            except OSError:
                pass
            return

        # Get creation time
        try:
            created_at = path.stat().st_mtime
        except OSError:
            return

        agent = Agent(id=agent_id, socket_path=path, created_at=created_at)

        with self._lock:
            if agent_id not in self._agents:
                self._agents[agent_id] = agent
                if emit_callback and self.on_agent_added:
                    self.on_agent_added(agent)

    def _handle_socket_deleted(self, path: Path) -> None:
        """Handle a socket file being deleted."""
        if path.name in INTERNAL_SOCKETS:
            return

        agent_id = path.stem

        with self._lock:
            if agent_id in self._agents:
                agent = self._agents.pop(agent_id)
                if self.on_agent_removed:
                    self.on_agent_removed(agent)


class _AgentEventHandler(FileSystemEventHandler):
    """Watchdog event handler for agent sockets."""

    def __init__(self, watcher: AgentWatcher) -> None:
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src_path = event.src_path if isinstance(event.src_path, str) else event.src_path.decode()
        path = Path(src_path)
        if path.suffix == ".sock":
            self._watcher._handle_socket_created(path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src_path = event.src_path if isinstance(event.src_path, str) else event.src_path.decode()
        path = Path(src_path)
        if path.suffix == ".sock":
            self._watcher._handle_socket_deleted(path)


def _is_socket_alive(path: Path) -> bool:
    """Check if a Unix socket has an active listener.

    Attempts to connect to the socket. If connection succeeds,
    there's a listener. If ECONNREFUSED, the socket is stale.

    Args:
        path: Path to the socket file.

    Returns:
        True if socket has a listener, False otherwise.
    """
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(str(path))
        s.close()
        return True
    except ConnectionRefusedError:
        # Socket exists but no one is listening (stale)
        return False
    except (FileNotFoundError, OSError):
        # Socket doesn't exist or other error
        return False


def discover_agents() -> list[str]:
    """One-shot discovery of running agents.

    Scans the socket directory for .sock files and returns agent IDs.
    Excludes internal sockets and stale sockets.

    Returns:
        List of agent IDs sorted by socket creation time.
    """
    socket_dir = get_socket_dir()
    if not socket_dir.exists():
        return []

    agents: list[tuple[str, float]] = []  # (id, mtime)

    for sock_file in socket_dir.glob("*.sock"):
        if sock_file.name in INTERNAL_SOCKETS:
            continue

        # Check if socket is alive
        if not _is_socket_alive(sock_file):
            # Stale socket, try to clean up
            try:
                sock_file.unlink()
            except OSError:
                pass
            continue

        try:
            mtime = sock_file.stat().st_mtime
            agents.append((sock_file.stem, mtime))
        except OSError:
            continue

    # Sort by creation time (oldest first)
    agents.sort(key=lambda x: x[1])
    return [agent_id for agent_id, _ in agents]
