"""Socket monitoring for agent discovery.

Provides pluggable monitoring strategies:
- WatchdogMonitor: Uses filesystem events (fast, but potentially unreliable)
- PollingMonitor: Polls directory periodically (reliable, 1-second delay)
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from voxtype.utils.platform import get_socket_dir

logger = logging.getLogger(__name__)

# Internal sockets to exclude from agent discovery
INTERNAL_SOCKETS = {"daemon.sock", "control.sock"}

@dataclass
class DiscoveredAgent:
    """Info about a discovered agent socket."""

    id: str
    socket_path: Path
    created_at: float  # mtime of socket file

class SocketMonitor(Protocol):
    """Protocol for socket directory monitors.

    Implementations watch the socket directory and notify when
    agent sockets appear or disappear.
    """

    on_agent_added: Callable[[DiscoveredAgent], None] | None
    on_agent_removed: Callable[[DiscoveredAgent], None] | None

    @property
    def agent_ids(self) -> list[str]:
        """Get list of discovered agent IDs, sorted by creation time."""
        ...

    def start(self) -> None:
        """Start monitoring."""
        ...

    def stop(self) -> None:
        """Stop monitoring."""
        ...

class BaseSocketMonitor(ABC):
    """Base class for socket monitors with common functionality."""

    def __init__(
        self,
        on_agent_added: Callable[[DiscoveredAgent], None] | None = None,
        on_agent_removed: Callable[[DiscoveredAgent], None] | None = None,
    ) -> None:
        self.on_agent_added = on_agent_added
        self.on_agent_removed = on_agent_removed
        self._agents: dict[str, DiscoveredAgent] = {}
        self._lock = threading.Lock()
        self._socket_dir: Path | None = None

    @property
    def agent_ids(self) -> list[str]:
        """Get list of agent IDs, sorted by creation time."""
        with self._lock:
            agents = sorted(self._agents.values(), key=lambda a: a.created_at)
            return [a.id for a in agents]

    @abstractmethod
    def start(self) -> None:
        """Start monitoring."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop monitoring."""
        ...

    def _add_agent(self, agent: DiscoveredAgent, *, emit_callback: bool = True) -> bool:
        """Add an agent if not already tracked.

        Returns True if agent was added (new), False if already exists.
        """
        with self._lock:
            if agent.id in self._agents:
                return False
            self._agents[agent.id] = agent

        if emit_callback and self.on_agent_added:
            self.on_agent_added(agent)
        return True

    def _remove_agent(self, agent_id: str) -> bool:
        """Remove an agent if tracked.

        Returns True if agent was removed, False if not found.
        """
        with self._lock:
            if agent_id not in self._agents:
                return False
            agent = self._agents.pop(agent_id)

        if self.on_agent_removed:
            self.on_agent_removed(agent)
        return True

    def _discover_socket(self, path: Path) -> DiscoveredAgent | None:
        """Check a socket file and return DiscoveredAgent if valid.

        Returns None if socket is invalid, stale, or internal.
        """
        if path.name in INTERNAL_SOCKETS:
            return None

        if not path.exists():
            return None

        agent_id = path.stem

        # Check if socket is alive (has a listener)
        if not is_socket_alive(path):
            # Stale socket, try to clean up
            try:
                path.unlink()
                logger.debug(f"Removed stale socket: {path}")
            except OSError:
                pass
            return None

        # Get creation time
        try:
            created_at = path.stat().st_mtime
        except OSError:
            return None

        return DiscoveredAgent(id=agent_id, socket_path=path, created_at=created_at)

class PollingMonitor(BaseSocketMonitor):
    """Socket monitor that polls the directory periodically.

    Reliable but with a small delay (default 1 second).
    Also checks if existing sockets are still alive.
    """

    def __init__(
        self,
        on_agent_added: Callable[[DiscoveredAgent], None] | None = None,
        on_agent_removed: Callable[[DiscoveredAgent], None] | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        """Initialize polling monitor.

        Args:
            on_agent_added: Callback when agent socket appears.
            on_agent_removed: Callback when agent socket disappears.
            poll_interval: Seconds between polls (default 1.0).
        """
        super().__init__(on_agent_added, on_agent_removed)
        self._poll_interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start polling."""
        if self._running:
            return

        self._socket_dir = get_socket_dir()
        self._running = True

        # Initial discovery (no callbacks)
        self._scan_directory(emit_callbacks=False)

        # Start polling thread
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="polling-socket-monitor",
        )
        self._thread.start()
        logger.debug(f"PollingMonitor started (interval={self._poll_interval}s)")

    def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.debug("PollingMonitor stopped")

    def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            time.sleep(self._poll_interval)
            if not self._running:
                break
            try:
                self._scan_directory(emit_callbacks=True)
            except Exception as e:
                logger.exception(f"Error in polling loop: {e}")

    def _scan_directory(self, *, emit_callbacks: bool = True) -> None:
        """Scan socket directory for changes."""
        if not self._socket_dir or not self._socket_dir.exists():
            return

        # Find current sockets
        current_sockets: dict[str, Path] = {}
        for sock_file in self._socket_dir.glob("*.sock"):
            if sock_file.name not in INTERNAL_SOCKETS:
                current_sockets[sock_file.stem] = sock_file

        # Check for new sockets
        for agent_id, sock_path in current_sockets.items():
            with self._lock:
                if agent_id in self._agents:
                    continue  # Already tracked

            # New socket - verify it's alive
            agent = self._discover_socket(sock_path)
            if agent:
                self._add_agent(agent, emit_callback=emit_callbacks)
                logger.debug(f"Discovered agent: {agent_id}")

        # Check for removed sockets or dead sockets
        with self._lock:
            tracked_ids = list(self._agents.keys())

        for agent_id in tracked_ids:
            if agent_id not in current_sockets:
                # Socket file removed
                self._remove_agent(agent_id)
                logger.debug(f"Agent socket removed: {agent_id}")
            else:
                # Socket file exists - check if still alive
                sock_path = current_sockets[agent_id]
                if not is_socket_alive(sock_path):
                    self._remove_agent(agent_id)
                    logger.debug(f"Agent socket dead: {agent_id}")
                    # Clean up stale socket
                    try:
                        sock_path.unlink()
                    except OSError:
                        pass

class WatchdogMonitor(BaseSocketMonitor):
    """Socket monitor using filesystem events via watchdog.

    Fast (near-instant) but may miss events on some platforms/configurations.
    """

    def __init__(
        self,
        on_agent_added: Callable[[DiscoveredAgent], None] | None = None,
        on_agent_removed: Callable[[DiscoveredAgent], None] | None = None,
    ) -> None:
        super().__init__(on_agent_added, on_agent_removed)
        self._observer: Any = None

    def start(self) -> None:
        """Start watching."""
        from watchdog.observers import Observer

        self._socket_dir = get_socket_dir()

        # Initial discovery (no callbacks)
        self._discover_existing(emit_callbacks=False)

        # Start filesystem watcher
        from watchdog.events import FileSystemEvent, FileSystemEventHandler

        class Handler(FileSystemEventHandler):
            def __init__(self, monitor: WatchdogMonitor) -> None:
                self._monitor = monitor

            def on_created(self, event: FileSystemEvent) -> None:
                if event.is_directory:
                    return
                src_path = event.src_path if isinstance(event.src_path, str) else event.src_path.decode()
                path = Path(src_path)
                if path.suffix == ".sock":
                    agent = self._monitor._discover_socket(path)
                    if agent:
                        self._monitor._add_agent(agent)
                        logger.debug(f"Watchdog: agent created: {agent.id}")

            def on_deleted(self, event: FileSystemEvent) -> None:
                if event.is_directory:
                    return
                src_path = event.src_path if isinstance(event.src_path, str) else event.src_path.decode()
                path = Path(src_path)
                if path.suffix == ".sock":
                    agent_id = path.stem
                    if agent_id not in INTERNAL_SOCKETS:
                        self._monitor._remove_agent(agent_id)
                        logger.debug(f"Watchdog: agent deleted: {agent_id}")

        self._observer = Observer()
        self._observer.schedule(Handler(self), str(self._socket_dir), recursive=False)
        self._observer.start()
        logger.debug("WatchdogMonitor started")

    def stop(self) -> None:
        """Stop watching."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
        logger.debug("WatchdogMonitor stopped")

    def _discover_existing(self, *, emit_callbacks: bool = True) -> None:
        """Discover agents that already exist."""
        if not self._socket_dir:
            return

        for sock_file in self._socket_dir.glob("*.sock"):
            agent = self._discover_socket(sock_file)
            if agent:
                self._add_agent(agent, emit_callback=emit_callbacks)

def is_socket_alive(path: Path) -> bool:
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

def create_monitor(
    monitor_type: str = "polling",
    on_agent_added: Callable[[DiscoveredAgent], None] | None = None,
    on_agent_removed: Callable[[DiscoveredAgent], None] | None = None,
    poll_interval: float = 1.0,
) -> BaseSocketMonitor:
    """Factory function to create a socket monitor.

    Args:
        monitor_type: "polling" or "watchdog"
        on_agent_added: Callback when agent appears.
        on_agent_removed: Callback when agent disappears.
        poll_interval: Seconds between polls (only for polling monitor).

    Returns:
        A SocketMonitor instance.
    """
    if monitor_type == "watchdog":
        return WatchdogMonitor(
            on_agent_added=on_agent_added,
            on_agent_removed=on_agent_removed,
        )
    else:
        return PollingMonitor(
            on_agent_added=on_agent_added,
            on_agent_removed=on_agent_removed,
            poll_interval=poll_interval,
        )
