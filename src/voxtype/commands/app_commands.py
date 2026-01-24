"""App-level commands (orchestrator domain)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from voxtype.commands.schema import CommandParam, CommandSchema, ParamType

if TYPE_CHECKING:
    from voxtype.core.app import VoxtypeApp


@dataclass
class CommandHandler:
    """A registered command with its handler."""

    schema: CommandSchema
    handler: Callable[..., None]


class AppCommands:
    """Registry of app-level commands.

    These are commands that control the VoxType app itself,
    not commands sent to targets.
    """

    def __init__(self, app: VoxtypeApp) -> None:
        self._app = app
        self._commands: dict[str, CommandHandler] = {}
        self._register_builtin()

    def _register_builtin(self) -> None:
        """Register built-in app commands."""
        # Listening control
        self.register(
            CommandSchema(
                name="listening-on",
                description="Start listening for voice input",
                category="listening",
            ),
            lambda: self._app._set_listening(True),
        )

        self.register(
            CommandSchema(
                name="listening-off",
                description="Stop listening for voice input",
                category="listening",
            ),
            lambda: self._app._set_listening(False),
        )

        self.register(
            CommandSchema(
                name="toggle-listening",
                description="Toggle listening on/off",
                category="listening",
            ),
            lambda: self._app._toggle_listening(),
        )

        # Mode control
        self.register(
            CommandSchema(
                name="toggle-mode",
                description="Switch between transcription and command mode",
                category="mode",
            ),
            lambda: self._app._switch_processing_mode(),
        )

        # Project/target switching
        self.register(
            CommandSchema(
                name="project-next",
                description="Switch to next project/target",
                category="project",
            ),
            lambda: self._app._switch_agent(1),
        )

        self.register(
            CommandSchema(
                name="project-prev",
                description="Switch to previous project/target",
                category="project",
            ),
            lambda: self._app._switch_agent(-1),
        )

        self.register(
            CommandSchema(
                name="switch-to-project",
                description="Switch to a specific project by name",
                category="project",
                params=[
                    CommandParam(
                        name="name",
                        type=ParamType.STRING,
                        description="Project name",
                        required=True,
                    )
                ],
            ),
            lambda name: self._app._switch_to_agent_by_name(name),
        )

        self.register(
            CommandSchema(
                name="switch-to-project-index",
                description="Switch to a specific project by index (1-based)",
                category="project",
                params=[
                    CommandParam(
                        name="index",
                        type=ParamType.INT,
                        description="Project index (1 = first)",
                        required=True,
                    )
                ],
            ),
            lambda index: self._app._switch_to_agent_by_index(index),
        )

        # Text operations
        self.register(
            CommandSchema(
                name="repeat",
                description="Repeat last sent text",
                category="text",
            ),
            lambda: self._app._repeat_last_injection(),
        )

        self.register(
            CommandSchema(
                name="discard",
                description="Discard current recording/buffer",
                category="text",
            ),
            lambda: self._app._discard_current(),
        )

    def register(self, schema: CommandSchema, handler: Callable[..., None]) -> None:
        """Register a command."""
        self._commands[schema.name] = CommandHandler(schema=schema, handler=handler)

    def execute(self, name: str, args: dict | None = None) -> bool:
        """Execute a command by name.

        Returns True if command was found and executed.
        """
        if name not in self._commands:
            return False

        cmd = self._commands[name]
        args = args or {}

        # Call handler with args
        try:
            if cmd.schema.params:
                cmd.handler(**args)
            else:
                cmd.handler()
            return True
        except Exception as e:
            if self._app.config.verbose:
                print(f"[command] Error executing {name}: {e}")
            return False

    def get_schema(self, name: str) -> CommandSchema | None:
        """Get command schema by name."""
        if name in self._commands:
            return self._commands[name].schema
        return None

    def list_schemas(self, category: str | None = None) -> list[CommandSchema]:
        """List all command schemas, optionally filtered by category."""
        schemas = [cmd.schema for cmd in self._commands.values()]
        if category:
            schemas = [s for s in schemas if s.category == category]
        return sorted(schemas, key=lambda s: s.name)

    def get_json_schemas(self) -> list[dict]:
        """Get all schemas in JSON format for LLM."""
        from voxtype.commands.schema import schemas_to_json

        return schemas_to_json(self.list_schemas())
