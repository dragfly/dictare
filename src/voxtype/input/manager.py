"""Input manager - coordinates all input sources."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from voxtype.input.base import InputCallback, InputEvent, InputSource
from voxtype.input.device import DeviceInputSource, DeviceProfile, HIDDeviceInputSource
from voxtype.input.keyboard import KeyBinding, KeyboardShortcutSource

if TYPE_CHECKING:
    from voxtype.commands.app_commands import AppCommands

class InputManager:
    """Manages all input sources and routes commands.

    Coordinates keyboard shortcuts, device profiles, and routes
    input events to the appropriate handler.
    """

    def __init__(
        self,
        app_commands: "AppCommands",
        verbose: bool = False,
    ) -> None:
        self._app_commands = app_commands
        self._verbose = verbose
        self._sources: list[InputSource] = []
        self._on_target_command: Callable[[InputEvent], None] | None = None

    def set_target_command_handler(
        self, handler: Callable[[InputEvent], None]
    ) -> None:
        """Set handler for commands that go to targets (not app commands)."""
        self._on_target_command = handler

    def load_keyboard_shortcuts(self, shortcuts: list[dict]) -> None:
        """Load keyboard shortcuts from config.

        Args:
            shortcuts: List of shortcut dicts with keys, command, and optional args
        """
        bindings = []

        for shortcut in shortcuts:
            keys_str = shortcut.get("keys", "")
            command = shortcut.get("command", "")
            args = shortcut.get("args")

            if not keys_str or not command:
                continue

            modifiers, key = KeyboardShortcutSource.parse_shortcut(keys_str)
            bindings.append(
                KeyBinding(
                    modifiers=modifiers,
                    key=key,
                    command=command,
                    args=args,
                )
            )

        if bindings:
            source = KeyboardShortcutSource(bindings)
            self._sources.append(source)
            if self._verbose:
                print(f"[input] Loaded {len(bindings)} keyboard shortcuts")

    def load_device_profiles(self, devices_dir: Path | None = None) -> None:
        """Load device profiles from directory.

        Args:
            devices_dir: Directory containing .toml device profiles

        On Linux: Uses evdev (DeviceInputSource) with device_match
        On macOS: Uses hidapi (HIDDeviceInputSource) with vendor_id/product_id
        """
        if devices_dir is None:
            devices_dir = Path.home() / ".config" / "voxtype" / "devices"

        if not devices_dir.exists():
            return

        for profile_file in devices_dir.glob("*.toml"):
            profile = DeviceProfile.load_from_file(profile_file)
            if not profile:
                continue

            source: InputSource | None = None

            # Try evdev first on Linux (preferred for device grabbing)
            if sys.platform == "linux" and profile.device_match:
                source = DeviceInputSource(profile, verbose=self._verbose)

            # Try hidapi on macOS, or as fallback on Linux if HID IDs configured
            if source is None and profile.has_hid_ids:
                source = HIDDeviceInputSource(profile, verbose=self._verbose)

            if source:
                self._sources.append(source)
                if self._verbose:
                    print(f"[input] Loaded device profile: {profile.name}")

    def start(self) -> None:
        """Start all input sources."""
        for source in self._sources:
            success = source.start(self._handle_input)
            if self._verbose:
                status = "started" if success else "failed"
                print(f"[input] {source.source_name}: {status}")

    def stop(self) -> None:
        """Stop all input sources."""
        for source in self._sources:
            source.stop()

    def _handle_input(self, event: InputEvent) -> None:
        """Handle input event from any source."""
        if self._verbose:
            print(f"[input] {event.source}: {event.command}")

        # Try to execute as app command first
        success = self._app_commands.execute(event.command, event.args)

        if success:
            return

        # Not an app command - route to target
        if self._on_target_command:
            self._on_target_command(event)
        elif self._verbose:
            print(f"[input] Unknown command: {event.command}")

    @property
    def source_count(self) -> int:
        """Get number of registered sources."""
        return len(self._sources)

    @property
    def running_sources(self) -> list[str]:
        """Get names of running sources."""
        return [s.source_name for s in self._sources if s.is_running]
