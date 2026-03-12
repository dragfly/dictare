"""Local IPC transport for macOS hotkey events.

Launcher -> engine transport over a Unix domain socket with per-event ACK.
Used to avoid blind SIGUSR1 delivery and enable end-to-end delivery checks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dictare.hotkey.runtime_status import clear_runtime_status, write_runtime_status

logger = logging.getLogger(__name__)

DEFAULT_SOCKET_PATH = Path.home() / ".dictare" / "hotkey.sock"


class HotkeyIPCServer:
    """Receive hotkey events over a Unix socket and reply with ACK.

    Supports two protocols:
    - Legacy: ``{"type":"hotkey.tap"}`` — single atomic event (SIGUSR1 replacement)
    - New:    ``{"type":"key.down"}`` / ``{"type":"key.up"}`` — raw press/release pair
              that feeds directly into TapDetector for long-press support.

    The new protocol is preferred; ``hotkey.tap`` is kept for SIGUSR1 fallback
    and for launchers that haven't been updated yet.
    """

    def __init__(
        self,
        on_tap: Callable[[], None],
        on_key_down: Callable[[], None] | None = None,
        on_key_up: Callable[[], None] | None = None,
        on_other_key: Callable[[], None] | None = None,
        on_combo: Callable[[], None] | None = None,
        socket_path: Path | None = None,
        accept_timeout: float = 0.5,
    ) -> None:
        self._on_tap = on_tap
        self._on_key_down = on_key_down
        self._on_key_up = on_key_up
        self._on_other_key = on_other_key
        self._on_combo = on_combo
        self._socket_path = socket_path or DEFAULT_SOCKET_PATH
        self._accept_timeout = accept_timeout
        self._server_sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._lock = threading.Lock()
        self._delivered_count = 0
        self._last_delivered_ts = 0.0
        self._confirmed_hash_saved = False

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
        server.settimeout(self._accept_timeout)
        self._server_sock = server

        self._running.set()
        self._thread = threading.Thread(target=self._serve_loop, name="hotkey-ipc", daemon=True)
        self._thread.start()
        self._write_runtime_status()
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
        clear_runtime_status()

    def _serve_loop(self) -> None:
        assert self._server_sock is not None
        while self._running.is_set():
            try:
                conn, _ = self._server_sock.accept()
            except TimeoutError:
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

            if msg_type == "hotkey.tap":
                try:
                    self._on_tap()
                    with self._lock:
                        self._delivered_count += 1
                        self._last_delivered_ts = time.time()
                        self._write_runtime_status_locked()
                except Exception:
                    logger.exception("Hotkey IPC callback failed (hotkey.tap)")
            elif msg_type == "key.down":
                try:
                    if self._on_key_down is not None:
                        self._on_key_down()
                    with self._lock:
                        self._delivered_count += 1
                        self._last_delivered_ts = time.time()
                        self._write_runtime_status_locked()
                except Exception:
                    logger.exception("Hotkey IPC callback failed (key.down)")
            elif msg_type == "key.up":
                try:
                    if self._on_key_up is not None:
                        self._on_key_up()
                    with self._lock:
                        self._delivered_count += 1
                        self._last_delivered_ts = time.time()
                        self._write_runtime_status_locked()
                except Exception:
                    logger.exception("Hotkey IPC callback failed (key.up)")
            elif msg_type == "other_key":
                try:
                    if self._on_other_key is not None:
                        self._on_other_key()
                except Exception:
                    logger.exception("Hotkey IPC callback failed (other_key)")
            elif msg_type == "key.combo":
                try:
                    if self._on_combo is not None:
                        self._on_combo()
                except Exception:
                    logger.exception("Hotkey IPC callback failed (key.combo)")
            else:
                logger.warning("Unknown hotkey IPC message type: %s", msg_type)
                return

            ack = json.dumps({"type": "ack", "seq": seq}) + "\n"
            conn.sendall(ack.encode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            logger.debug("Invalid hotkey IPC payload", exc_info=True)
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _write_runtime_status(self) -> None:
        with self._lock:
            self._write_runtime_status_locked()

    def _write_runtime_status_locked(self) -> None:
        permission_status = self._read_launcher_status()
        status = "unknown"
        if self._delivered_count > 0:
            status = "confirmed"
            if not self._confirmed_hash_saved:
                self._save_confirmed_launcher_hash()
                self._confirmed_hash_saved = True
        elif permission_status == "failed":
            status = "failed"
        elif permission_status in ("active", "confirmed"):
            status = "active"

        payload = {
            "status": status,
            "permission_status": permission_status,
            "capture_healthy": self._delivered_count > 0,
            "active_provider": "ipc" if self._delivered_count > 0 else "none",
            "delivered_count": self._delivered_count,
            "deduped_count": 0,
            "last_delivered_ts": self._last_delivered_ts,
            "providers": {
                "ipc": {
                    "enabled": True,
                    "running": self._running.is_set(),
                    "healthy": True,
                    "event_count": self._delivered_count,
                    "last_event_ts": self._last_delivered_ts or None,
                    "last_error": "",
                },
                "signal": {
                    "enabled": True,
                    "running": False,
                    "healthy": False,
                    "event_count": 0,
                    "last_event_ts": None,
                    "last_error": "",
                },
            },
        }
        write_runtime_status(payload)

    @staticmethod
    def _save_confirmed_launcher_hash() -> None:
        """Save launcher binary hash when hotkey is first confirmed.

        TCC (Input Monitoring) trust is tied to the binary — if it hasn't
        changed since last confirmation, the trust is still valid and we
        can skip the "confirming" phase on next restart.
        """
        try:
            from dictare.daemon.app_bundle import get_app_path

            launcher = get_app_path() / "Contents" / "MacOS" / "Dictare"
            if not launcher.exists():
                return
            h = hashlib.sha256(launcher.read_bytes()).hexdigest()
            confirmed_file = Path.home() / ".dictare" / "hotkey_confirmed_hash"
            confirmed_file.write_text(h, encoding="utf-8")
            logger.debug("Saved confirmed launcher hash: %s", h[:12])
        except Exception:
            logger.debug("Failed to save confirmed launcher hash", exc_info=True)

    @staticmethod
    def _read_launcher_status() -> str:
        status_file = Path.home() / ".dictare" / "hotkey_status"
        try:
            return status_file.read_text().strip()
        except FileNotFoundError:
            return "unknown"


def check_confirmed_launcher_hash() -> bool:
    """Check if current launcher binary matches the previously confirmed hash.

    Returns True if the binary hasn't changed since hotkey was last confirmed,
    meaning TCC trust is still valid and we can skip the "confirming" phase.
    """
    try:
        from dictare.daemon.app_bundle import get_app_path

        launcher = get_app_path() / "Contents" / "MacOS" / "Dictare"
        confirmed_file = Path.home() / ".dictare" / "hotkey_confirmed_hash"
        if not launcher.exists() or not confirmed_file.exists():
            return False
        current = hashlib.sha256(launcher.read_bytes()).hexdigest()
        saved = confirmed_file.read_text(encoding="utf-8").strip()
        return current == saved
    except Exception:
        return False
