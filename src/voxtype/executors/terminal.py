"""Terminal executor - injects text via keyboard simulation."""

from __future__ import annotations

import sys

from voxtype.executors.base import CommandEvent, Executor, TargetConfig


class TerminalExecutor(Executor):
    """Executor for terminal target.

    Injects text directly into the terminal via keyboard simulation.
    """

    VERSION = "1.0.0"

    def __init__(self, config: TargetConfig) -> None:
        super().__init__(config)
        self._method = config.config.get("method", "keyboard")  # keyboard or agent
        self._typing_delay_ms = config.config.get("typing_delay_ms", 5)
        self._auto_submit = config.config.get("auto_submit", False)
        self._injector = None

    @property
    def target_type(self) -> str:
        return "terminal"

    def _get_injector(self):
        """Lazy-load the text injector."""
        if self._injector is None:
            from voxtype.injection.base import TextInjector

            self._injector = TextInjector(
                method=self._method,
                typing_delay_ms=self._typing_delay_ms,
            )
        return self._injector

    def execute(self, event: CommandEvent) -> bool:
        """Execute a terminal command."""
        if event.command == "send-text":
            text = event.args.get("text", "")
            return self._inject_text(text)
        elif event.command == "submit":
            return self._press_enter()
        return False

    def _inject_text(self, text: str) -> bool:
        """Inject text into terminal."""
        try:
            injector = self._get_injector()
            injector.inject(text)
            return True
        except Exception:
            return False

    def _press_enter(self) -> bool:
        """Press Enter key."""
        try:
            if sys.platform == "darwin":
                import subprocess

                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        'tell application "System Events" to keystroke return',
                    ],
                    check=True,
                    capture_output=True,
                )
            else:
                # Linux - use ydotool or similar
                injector = self._get_injector()
                injector.inject("\n")
            return True
        except Exception:
            return False

    def get_supported_commands(self) -> list[str]:
        return ["send-text", "submit"]

    def send_text(self, text: str, auto_submit: bool | None = None) -> bool:
        """Convenience method to send text."""
        event = CommandEvent(command="send-text", args={"text": text})
        success = self.execute(event)

        if success and (auto_submit if auto_submit is not None else self._auto_submit):
            submit_event = CommandEvent(command="submit")
            self.execute(submit_event)

        return success
