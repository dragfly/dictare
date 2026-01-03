"""Base input source interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class InputEvent:
    """An input event that triggers a command."""

    command: str
    args: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"  # e.g., "keyboard", "device:presenter", "voice"


InputCallback = Callable[[InputEvent], None]


class InputSource(ABC):
    """Abstract base class for input sources.

    Input sources listen for user input (keyboard shortcuts, device buttons)
    and emit InputEvents. They know nothing about what commands do - they just
    emit command names and arguments.
    """

    @abstractmethod
    def start(self, on_input: InputCallback) -> bool:
        """Start listening for input.

        Args:
            on_input: Callback when an input triggers a command.

        Returns:
            True if started successfully.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop listening for input."""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Get human-readable name of this input source."""
        pass

    @property
    def is_running(self) -> bool:
        """Check if the source is currently running."""
        return False
