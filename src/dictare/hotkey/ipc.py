"""Local IPC transport for macOS hotkey events.

Launcher -> engine transport over a Unix domain socket with per-event ACK.
Used to avoid blind SIGUSR1 delivery and enable end-to-end delivery checks.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_SOCKET_PATH = Path.home() / ".dictare" / "hotkey.sock"

class HotkeyIPCServer:
    """Receive hotkey tap events over a Unix socket and reply with ACK."""

    def __init__(self, on_tap: Callable[[], None], socket_path: Path | None = None) -> None:
        self._on_tap = on_tap
        self._socket_path = socket_path or DEFAULT_SOCKET_PATH
        self._server_sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    def start(self) -> None:
        if self._running.is_set():
            return

        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._socket_path.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "Failed to remove stale hotkey socket: %s",
                self._socket_path,
                exc_info=True,
            )

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self._socket_path))
        os.chmod(self._socket_path, 0o600)
        server.listen(16)
        server.settimeout(0.5)
        self._server_sock = server

        self._running.set()
        self._thread = threading.Thread(target=self._serve_loop, name="hotkey-ipc", daemon=True)
        self._thread.start()
        logger.info("Hotkey IPC server listening on %s", self._socket_path)

    def stop(self) -> None:
        self._running.clear()

        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

        try:
            self._socket_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _serve_loop(self) -> None:
        assert self._server_sock is not None
        while self._running.is_set():
            try:
                conn, _ = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()

    def _handle_conn(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(1.0)
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk

            line = data.split(b"\n", 1)[0].decode("utf-8", errors="replace")
            msg: dict[str, Any] = json.loads(line)
            msg_type = str(msg.get("type", ""))
            seq = int(msg.get("seq", -1))

            if msg_type != "hotkey.tap":
                logger.warning("Unknown hotkey IPC message type: %s", msg_type)
                return

            try:
                self._on_tap()
            except Exception:
                logger.exception("Hotkey IPC callback failed")

            ack = json.dumps({"type": "ack", "seq": seq}) + "\n"
            conn.sendall(ack.encode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            logger.debug("Invalid hotkey IPC payload", exc_info=True)
        finally:
            try:
                conn.close()
            except OSError:
                pass
