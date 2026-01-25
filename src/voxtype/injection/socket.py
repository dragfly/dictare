"""Unix socket text injection - sends OpenVIP messages via socket."""

from __future__ import annotations

import json
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path

from voxtype import __version__
from voxtype.injection.base import TextInjector

# OpenVIP protocol version
OPENVIP_VERSION = "1.0"


def get_socket_path(agent_id: str) -> Path:
    """Get Unix socket path for an agent.

    Args:
        agent_id: Agent identifier.

    Returns:
        Path to socket file.
    """
    return Path(f"/tmp/voxtype-{agent_id}.sock")


class SocketInjector(TextInjector):
    """Sends OpenVIP messages to a Unix socket.

    The agent (consumer) listens on the socket and receives messages.
    """

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.socket_path = get_socket_path(agent_id)

    def is_available(self) -> bool:
        """Check if the agent socket exists."""
        return self.socket_path.exists()

    def _send_message(self, msg: dict) -> bool:
        """Send an OpenVIP message to the socket."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(str(self.socket_path))
                data = json.dumps(msg, ensure_ascii=False) + "\n"
                sock.sendall(data.encode("utf-8"))
            return True
        except (OSError, ConnectionRefusedError):
            return False

    def _openvip_message(self, msg_type: str, **kwargs) -> dict:
        """Create an OpenVIP message."""
        msg = {
            "openvip": OPENVIP_VERSION,
            "type": msg_type,
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": f"voxtype/{__version__}",
        }
        msg.update(kwargs)
        return msg

    def type_text(self, text: str, delay_ms: int = 0, auto_enter: bool = True) -> bool:
        """Send text as OpenVIP message.

        The receiver (mux.py) handles message termination:
        - x_submit=true: text + Enter (submit)
        - x_visual_newline=true: text + Alt+Enter (visual newline)

        Args:
            text: Text to send (without trailing newline).
            delay_ms: Ignored for socket output.
            auto_enter: If True, receiver sends Enter. If False, sends visual newline.

        Returns:
            True if successful.
        """
        msg = self._openvip_message("message", text=text)
        if auto_enter:
            msg["x_submit"] = True
        else:
            msg["x_visual_newline"] = True

        return self._send_message(msg)

    def get_name(self) -> str:
        """Get the name of this injector."""
        return f"socket:{self.agent_id}"

    def send_newline(self) -> bool:
        """Send a standalone visual newline."""
        msg = self._openvip_message("message", text="\n")
        return self._send_message(msg)

    def send_submit(self) -> bool:
        """Send a submit message (Enter key)."""
        msg = self._openvip_message("message", text="", x_submit=True)
        return self._send_message(msg)
