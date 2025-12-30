"""Abstract base classes for window management."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Window:
    """Represents a window."""

    id: str  # Window ID (platform-specific)
    name: str  # Window title
    class_name: str  # Window class (e.g., "kitty", "firefox")
    pid: Optional[int] = None  # Process ID


class WindowManager(ABC):
    """Abstract base class for window management."""

    def __init__(self) -> None:
        """Initialize window manager."""
        self._target: Optional[Window] = None

    @abstractmethod
    def find_windows(self, query: str) -> list[Window]:
        """Find windows matching a query.

        Args:
            query: Search query (name, class, or pattern).

        Returns:
            List of matching windows.
        """
        pass

    @abstractmethod
    def list_windows(self) -> list[Window]:
        """List all windows.

        Returns:
            List of all windows.
        """
        pass

    @abstractmethod
    def get_active_window(self) -> Optional[Window]:
        """Get the currently focused window.

        Returns:
            Active window or None.
        """
        pass

    @abstractmethod
    def send_text(self, text: str, window: Optional[Window] = None) -> bool:
        """Send text to a window.

        Args:
            text: Text to type.
            window: Target window (uses target or active if None).

        Returns:
            True if successful.
        """
        pass

    @abstractmethod
    def focus_window(self, window: Window) -> bool:
        """Focus a window.

        Args:
            window: Window to focus.

        Returns:
            True if successful.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if window manager is available.

        Returns:
            True if available.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the name of this window manager.

        Returns:
            Human-readable name.
        """
        pass

    def set_target(self, window: Window) -> None:
        """Set the target window for text injection.

        Args:
            window: Window to use as target.
        """
        self._target = window

    def get_target(self) -> Optional[Window]:
        """Get the current target window.

        Returns:
            Current target window or None.
        """
        return self._target

    def clear_target(self) -> None:
        """Clear the target window (use active window instead)."""
        self._target = None
