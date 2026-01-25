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
        self._newline_sent = False

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

        Args:
            text: Text to send.
            delay_ms: Ignored for socket output.
            auto_enter: If True, include submit flag.

        Returns:
            True if successful.
        """
        # Handle trailing newline
        has_visual_newline = text.endswith("\n")
        if has_visual_newline:
            text = text.rstrip("\n")

        # Build message with voxtype-specific extension for submit
        msg = self._openvip_message("message", text=text)
        if auto_enter:
            msg["x_submit"] = True
        if has_visual_newline and not auto_enter:
            msg["x_visual_newline"] = True
            self._newline_sent = True  # Track so send_newline() can skip
        else:
            self._newline_sent = False

        return self._send_message(msg)

    def get_name(self) -> str:
        """Get the name of this injector."""
        return f"socket:{self.agent_id}"

    def send_newline(self) -> bool:
        """Send a visual newline.

        Note: When type_text() is called with auto_enter=false, the newline
        is already included via x_visual_newline flag. This method checks
        _newline_sent to avoid duplicates.
        """
        # Skip if newline was already sent by type_text()
        if self._newline_sent:
            self._newline_sent = False  # Reset for next call
            return True
        msg = self._openvip_message("message", text="\n")
        return self._send_message(msg)

    def send_submit(self) -> bool:
        """Send a submit message (Enter key)."""
        msg = self._openvip_message("message", text="", x_submit=True)
        return self._send_message(msg)
