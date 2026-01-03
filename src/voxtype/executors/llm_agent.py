"""LLM Agent executor - writes JSONL to file."""

from __future__ import annotations

import json
from pathlib import Path

from voxtype.executors.base import CommandEvent, Executor, TargetConfig


class LLMAgentExecutor(Executor):
    """Executor for LLM agent targets.

    Writes commands as JSONL to a file, which can be read by
    InputMux or similar tools to feed to an LLM agent.
    """

    VERSION = "1.0.0"

    def __init__(self, config: TargetConfig) -> None:
        super().__init__(config)
        self._path = Path(config.config.get("path", f"/tmp/{config.id}.voxtype"))
        self._auto_submit = config.config.get("auto_submit", False)

    @property
    def target_type(self) -> str:
        return "llmAgent"

    def execute(self, event: CommandEvent) -> bool:
        """Write command to JSONL file."""
        try:
            line = json.dumps(event.to_dict(), ensure_ascii=False)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return True
        except Exception:
            return False

    def get_supported_commands(self) -> list[str]:
        return ["send-text", "submit"]

    def send_text(self, text: str, auto_submit: bool | None = None) -> bool:
        """Convenience method to send text.

        Args:
            text: The text to send
            auto_submit: Override auto_submit setting
        """
        event = CommandEvent(command="send-text", args={"text": text})
        success = self.execute(event)

        if success and (auto_submit if auto_submit is not None else self._auto_submit):
            submit_event = CommandEvent(command="submit")
            self.execute(submit_event)

        return success

    @property
    def path(self) -> Path:
        """Get the output file path."""
        return self._path
