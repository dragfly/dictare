"""File agent - sends messages via file (JSONL append).

This agent writes OpenVIP messages to a file that the agent mux reads.
More reliable than socket - no message loss.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from voxtype import __version__
from voxtype.agent.base import BaseAgent, OpenVIPMessage

logger = logging.getLogger(__name__)

def get_file_path(agent_id: str) -> Path:
    """Get file path for an agent.

    Uses ~/.local/share/voxtype/agents/ for agent files.

    Args:
        agent_id: Agent identifier.

    Returns:
        Path to file (e.g., ~/.local/share/voxtype/agents/claude.jsonl).
    """
    file_dir = Path.home() / ".local" / "share" / "voxtype" / "agents"
    file_dir.mkdir(parents=True, exist_ok=True)
    return file_dir / f"{agent_id}.jsonl"

class FileAgent(BaseAgent):
    """Agent that sends messages via file (JSONL append).

    Messages are appended to a file that the agent mux reads (tail -f style).
    More reliable than socket - no message loss due to buffer issues.
    """

    def __init__(self, agent_id: str) -> None:
        """Initialize file agent.

        Args:
            agent_id: Agent identifier (filename without .jsonl).
        """
        super().__init__(agent_id)
        self.file_path = get_file_path(agent_id)

    def is_available(self) -> bool:
        """Check if the agent file exists."""
        return self.file_path.exists()

    def is_alive(self) -> bool:
        """Check if the agent is active.

        For file-based, we just check if file exists.
        The agent mux creates the file when it starts.
        """
        return self.file_path.exists()

    def send(self, message: OpenVIPMessage) -> bool:
        """Send an OpenVIP message by appending to file.

        Args:
            message: OpenVIP message dict to send.

        Returns:
            True if written successfully, False otherwise.
        """
        try:
            # Add metadata
            msg = dict(message)
            msg["_written_ts"] = datetime.now(timezone.utc).isoformat()
            msg["_written_v"] = __version__

            data = json.dumps(msg, ensure_ascii=False) + "\n"

            with open(self.file_path, "a") as f:
                f.write(data)
                f.flush()

            return True
        except OSError as e:
            logger.debug(f"Failed to write to {self._id}: {e}")
            return False

    def __repr__(self) -> str:
        return f"FileAgent(id={self._id!r}, file={self.file_path})"
