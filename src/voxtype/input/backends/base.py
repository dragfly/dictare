"""Base class for device input backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

class DeviceBackend(ABC):
    """Abstract base class for device input backends.

    Each backend handles a specific way of receiving input from
    dedicated devices (presenter remotes, macro pads, etc.).

    Backends:
        - hidapi: Direct HID access, no device grab (works everywhere)
        - karabiner: Uses Karabiner-Elements for device grab (macOS only)
        - evdev: Linux evdev with device grab (Linux only)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name for display."""
        ...

    @property
    @abstractmethod
    def supports_grab(self) -> bool:
        """Whether this backend supports exclusive device grab."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available on the current system."""
        ...

    @abstractmethod
    def list_devices(self) -> list[dict]:
        """List available devices.

        Returns:
            List of device dicts with keys: vendor_id, product_id,
            manufacturer, product, path (backend-specific)
        """
        ...

    @abstractmethod
    def start(
        self,
        device_id: str,
        bindings: dict[str, str],
        on_command: Callable[[str, dict], None],
    ) -> bool:
        """Start listening to a device.

        Args:
            device_id: Device identifier (vendor:product or path)
            bindings: Key name -> command mapping
            on_command: Callback(command, args) when command triggered

        Returns:
            True if started successfully
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop listening."""
        ...

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Whether the backend is currently listening."""
        ...
