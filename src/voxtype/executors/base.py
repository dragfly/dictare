"""Base executor interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

@dataclass
class TargetConfig:
    """Configuration for a target instance."""

    id: str
    name: str
    type: str  # TargetType name
    config: dict[str, Any] = field(default_factory=dict)

@dataclass
class CommandEvent:
    """A command to be executed on a target."""

    command: str
    args: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "command": self.command,
            "args": self.args if self.args else None,
        }

class Executor(ABC):
    """Base class for target executors.

    An executor knows HOW to send commands to a specific target type.
    """

    VERSION = "1.0.0"

    def __init__(self, config: TargetConfig) -> None:
        self.config = config

    @property
    @abstractmethod
    def target_type(self) -> str:
        """The target type this executor handles."""
        pass

    @abstractmethod
    def execute(self, event: CommandEvent) -> bool:
        """Execute a command.

        Returns True if successful.
        """
        pass

    @abstractmethod
    def get_supported_commands(self) -> list[str]:
        """Get list of command names this executor supports."""
        pass

    def supports_command(self, command: str) -> bool:
        """Check if this executor supports a command."""
        return command in self.get_supported_commands()
