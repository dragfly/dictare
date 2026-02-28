from __future__ import annotations

import json
import os
import socket
import time
import uuid
from pathlib import Path

from dictare.hotkey.ipc import HotkeyIPCServer


def _short_socket_path() -> Path:
    # macOS AF_UNIX has a short path limit (~104 bytes including terminator).
    return Path("/tmp") / f"dictare-hk-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"


def _send_line(path: Path, payload: str) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(1.0)
        client.connect(str(path))
        client.sendall(payload.encode("utf-8"))
        data = client.recv(1024)
        return data.decode("utf-8")


def test_hotkey_ipc_ack_and_callback() -> None:
    calls: list[str] = []
    path = _short_socket_path()
    srv = HotkeyIPCServer(on_tap=lambda: calls.append("tap"), socket_path=path)
    srv.start()
    try:
        response = _send_line(path, '{"type":"hotkey.tap","seq":7,"ts":1.23}\n')
        assert calls == ["tap"]
        ack = json.loads(response.strip())
        assert ack == {"type": "ack", "seq": 7}
    finally:
        srv.stop()


def test_hotkey_ipc_ignores_invalid_payload() -> None:
    calls: list[str] = []
    path = _short_socket_path()
    srv = HotkeyIPCServer(on_tap=lambda: calls.append("tap"), socket_path=path)
    srv.start()
    try:
        # Unknown type: no callback, no ACK required.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.0)
            client.connect(str(path))
            client.sendall(b'{"type":"other","seq":1}\n')
            time.sleep(0.05)
        assert calls == []
    finally:
        srv.stop()
