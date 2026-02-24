"""KeyboardBindingManager - manages hotkeys, shortcuts, and device profiles.

Translates user input (key presses, device buttons) into AppController commands.

Responsibilities:
- Hotkey binding (e.g., ScrollLock → toggle_listening)
- Keyboard shortcuts (e.g., Ctrl+Alt+→ → next_agent)
- Device profiles (e.g., presenter buttons)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dictare.app.controller import AppController
    from dictare.config import Config

logger = logging.getLogger(__name__)

class KeyboardBindingManager:
    """Manages keyboard bindings and input sources.

    Connects input events (hotkeys, shortcuts, devices) to AppController commands.
    """

    def __init__(self, controller: AppController, config: Config) -> None:
        """Initialize the binding manager.

        Args:
            controller: AppController to send commands to.
            config: Application configuration.
        """
        self._controller = controller
        self._config = config
        self._input_manager: Any = None  # InputManager
        self._running = False

    def start(self) -> None:
        """Start all input sources (hotkey, shortcuts, devices)."""
        if self._running:
            return

        from dictare.input.manager import InputManager

        # Create InputManager with command handler
        self._input_manager = InputManager(
            app_commands=self._create_command_handler(),
            verbose=self._config.verbose,
        )

        # Load keyboard shortcuts from config
        if self._config.keyboard.shortcuts:
            self._input_manager.load_keyboard_shortcuts(self._config.keyboard.shortcuts)

        # Load device profiles (presenter, clicker, etc.)
        self._input_manager.load_device_profiles()

        # Start all sources
        self._input_manager.start()

        self._running = True

        if self._config.verbose and self._input_manager.running_sources:
            sources = ", ".join(self._input_manager.running_sources)
            logger.info(f"Input sources started: {sources}")

    def stop(self) -> None:
        """Stop all input sources."""
        if not self._running:
            return

        if self._input_manager:
            self._input_manager.stop()
            self._input_manager = None

        self._running = False
        logger.debug("KeyboardBindingManager stopped")

    def _create_command_handler(self) -> _BindingCommands:
        """Create command handler that routes to AppController."""
        return _BindingCommands(self._controller)

    @property
    def is_running(self) -> bool:
        """Check if bindings are active."""
        return self._running

    @property
    def active_sources(self) -> list[str]:
        """Get list of active input source names."""
        if self._input_manager:
            return self._input_manager.running_sources
        return []

class _BindingCommands:
    """Command handler that routes InputManager commands to AppController.

    This bridges the InputManager (which expects an AppCommands-like interface)
    to the AppController (which has the actual implementation).
    """

    def __init__(self, controller: AppController) -> None:
        self._controller = controller
        self._commands: dict[str, Callable[..., None]] = {
            "listening-on": lambda: self._set_listening(True),
            "listening-off": lambda: self._set_listening(False),
            "toggle-listening": self._controller.toggle_listening,
            "next-agent": self._controller.next_agent,
            "prev-agent": self._controller.prev_agent,
            "switch-to-agent": self._switch_to_agent,
            "switch-to-agent-index": self._switch_to_agent_index,
            "repeat": self._controller.repeat_last,
        }

    def execute(self, name: str, args: dict | None = None) -> bool:
        """Execute a command by name.

        Args:
            name: Command name.
            args: Optional arguments.

        Returns:
            True if command was found and executed.
        """
        if name not in self._commands:
            return False

        try:
            handler = self._commands[name]
            if args:
                handler(**args)
            else:
                handler()
            return True
        except Exception as e:
            logger.warning(f"Command error {name}: {e}")
            return False

    def _set_listening(self, on: bool) -> None:
        """Set listening state (idempotent)."""
        engine = self._controller.engine
        if engine:
            engine.set_listening(on)

    def _switch_to_agent(self, name: str) -> None:
        """Switch to agent by name."""
        self._controller.switch_to_agent(name)

    def _switch_to_agent_index(self, index: int) -> None:
        """Switch to agent by index."""
        self._controller.switch_to_agent_index(index)
