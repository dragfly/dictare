"""KeyboardBindingManager - manages hotkeys, shortcuts, and device profiles.

Translates user input (key presses, device buttons) into engine commands.

Responsibilities:
- Hotkey binding (e.g., ScrollLock → toggle_listening)
- Keyboard shortcuts (e.g., Ctrl+Alt+→ → next agent)
- Device profiles (e.g., presenter buttons)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dictare.config import Config
    from dictare.core.engine import DictareEngine

logger = logging.getLogger(__name__)

class KeyboardBindingManager:
    """Manages keyboard bindings and input sources.

    Connects input events (hotkeys, shortcuts, devices) to engine commands.
    """

    def __init__(self, engine: DictareEngine, config: Config) -> None:
        """Initialize the binding manager.

        Args:
            engine: Engine to send commands to.
            config: Application configuration.
        """
        self._engine = engine
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
            verbose=self._config.log_level == "debug",
        )

        # Load keyboard shortcuts from config
        if self._config.keyboard.shortcuts:
            self._input_manager.load_keyboard_shortcuts(self._config.keyboard.shortcuts)

        # Load device profiles (presenter, clicker, etc.)
        self._input_manager.load_device_profiles()

        # Start all sources
        self._input_manager.start()

        self._running = True

        if self._config.log_level == "debug" and self._input_manager.running_sources:
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
        """Create command handler that routes to the engine."""
        return _BindingCommands(self._engine)

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
    """Command handler that routes InputManager commands to the engine.

    This bridges the InputManager (which expects an AppCommands-like interface)
    to the DictareEngine (which has the actual implementation).
    """

    def __init__(self, engine: DictareEngine) -> None:
        self._commands: dict[str, Callable[..., Any]] = {
            "listening-on": lambda: engine.set_listening(True),
            "listening-off": lambda: engine.set_listening(False),
            "toggle-listening": engine.toggle_listening,
            "next-agent": lambda: engine.switch_agent(1),
            "prev-agent": lambda: engine.switch_agent(-1),
            "switch-to-agent": engine.switch_to_agent_by_name,
            "switch-to-agent-index": engine.switch_to_agent_by_index,
            "repeat": engine.resend_last,
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
