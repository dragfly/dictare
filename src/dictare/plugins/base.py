"""Plugin protocol and base classes for dictare plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import typer

    from dictare.services import ServiceRegistry

@runtime_checkable
class Plugin(Protocol):
    """Protocol for dictare plugins.

    Plugins can add CLI commands and access dictare services (STT, TTS, etc.).
    """

    @property
    def name(self) -> str:
        """Plugin name (used as CLI subcommand: dictare <name> ...).

        Should be lowercase with hyphens (e.g., "voice-tool").
        """
        ...

    @property
    def description(self) -> str:
        """Short description for CLI help."""
        ...

    def get_commands(self) -> typer.Typer | None:
        """Get CLI commands for this plugin.

        Returns:
            A typer.Typer instance with plugin commands, or None if no commands.
        """
        ...

    def on_load(self, services: ServiceRegistry) -> None:
        """Called when plugin is loaded.

        Use this to store reference to services for later use.

        Args:
            services: Service registry with STT, TTS, etc.
        """
        ...

class BasePlugin(ABC):
    """Base class for plugins with common functionality.

    Provides default implementations and helper methods.
    """

    def __init__(self) -> None:
        """Initialize plugin."""
        self._services: ServiceRegistry | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name (used as CLI subcommand)."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description for CLI help."""
        pass

    @property
    def services(self) -> ServiceRegistry:
        """Get service registry.

        Raises:
            RuntimeError: If plugin not loaded yet.
        """
        if self._services is None:
            raise RuntimeError(
                f"Plugin '{self.name}' not loaded. Call on_load() first."
            )
        return self._services

    @abstractmethod
    def get_commands(self) -> typer.Typer | None:
        """Get CLI commands for this plugin."""
        pass

    def on_load(self, services: ServiceRegistry) -> None:
        """Called when plugin is loaded.

        Args:
            services: Service registry with STT, TTS, etc.
        """
        self._services = services
