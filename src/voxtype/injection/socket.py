"""Unix socket text injection - sends OpenVIP messages via socket."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

from voxtype.core.openvip import create_message
from voxtype.injection.base import TextInjector


def get_socket_path(agent_id: str) -> Path:
    """Get Unix socket path for an agent.

    Args:
        agent_id: Agent identifier.

    Returns:
        Path to socket file in the platform-appropriate runtime directory.
    """
    from voxtype.utils.platform import get_socket_dir

    return get_socket_dir() / f"{agent_id}.sock"


class SocketInjector(TextInjector):
    """Sends OpenVIP messages to a Unix socket.

    The agent (consumer) listens on the socket and receives messages.
    Transports are transparent: they forward pre-built messages without modification.
    """

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.socket_path = get_socket_path(agent_id)

    def is_available(self) -> bool:
        """Check if the agent socket exists."""
        return self.socket_path.exists()

    def _send_raw(self, msg: dict[str, Any]) -> bool:
        """Send a message dict to the socket.

        Args:
            msg: OpenVIP message dict to send.

        Returns:
            True if sent successfully.
        """
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(str(self.socket_path))
                data = json.dumps(msg, ensure_ascii=False) + "\n"
                sock.sendall(data.encode("utf-8"))
            return True
        except (OSError, ConnectionRefusedError):
            return False

    def send_message(self, message: dict[str, Any]) -> bool:
        """Send a pre-built OpenVIP message.

        This is the preferred method - engine creates message with ID,
        transport forwards it transparently.

        Args:
            message: Complete OpenVIP message dict.

        Returns:
            True if sent successfully.
        """
        return self._send_raw(message)

    def type_text(
        self,
        text: str,
        delay_ms: int = 0,
        auto_enter: bool = True,
        submit_keys: str = "enter",
        newline_keys: str = "alt+enter",
    ) -> bool:
        """Send text as OpenVIP message.

        Note: Prefer send_message() when you have a pre-built message.
        This method creates a new message (for backward compatibility).

        Args:
            text: Text to send (without trailing newline).
            delay_ms: Ignored for socket output.
            auto_enter: If True, receiver sends Enter. If False, sends visual newline.
            submit_keys: Ignored for socket output (receiver handles keys).
            newline_keys: Ignored for socket output (receiver handles keys).

        Returns:
            True if successful.
        """
        msg = create_message(text, submit=auto_enter, visual_newline=not auto_enter)
        return self._send_raw(msg)

    def get_name(self) -> str:
        """Get the name of this injector."""
        return f"socket:{self.agent_id}"

    def send_newline(self) -> bool:
        """Send a standalone visual newline."""
        msg = create_message("\n")
        return self._send_raw(msg)

    def send_submit(self) -> bool:
        """Send a submit message (Enter key)."""
        msg = create_message("", submit=True)
        return self._send_raw(msg)
