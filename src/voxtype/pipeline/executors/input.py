"""Input executor.

Handles x_input messages by calling the write function with submit action.
Messages with x_input are consumed after execution.
Messages without x_input pass through unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from voxtype.pipeline.base import PipelineResult

logger = logging.getLogger(__name__)

@dataclass
class InputExecutor:
    """Executor that handles text input actions.

    When a message has x_input with submit=True, calls write_fn
    with the text and submit flag, then consumes the message.

    Attributes:
        write_fn: Callable that performs the actual text output.
                  Signature: write_fn(text: str, submit: bool) -> None
    """

    write_fn: Any  # Callable[[str, bool], None]

    @property
    def name(self) -> str:
        return "input"

    @property
    def field(self) -> str:
        return "x_input"

    def process(self, message: dict) -> PipelineResult:
        """Process message, executing input action if requested.

        Args:
            message: OpenVIP message dict.

        Returns:
            CONSUMED if input action executed, PASS otherwise.
        """
        x_input = message.get("x_input", {})
        if not x_input:
            return PipelineResult.passed(message)

        submit = x_input.get("submit", False) if isinstance(x_input, dict) else bool(x_input)
        text = message.get("text", "")

        # Append visual newline if requested by x_input
        if isinstance(x_input, dict) and x_input.get("newline"):
            text = text + "\n" if text else "\n"

        self.write_fn(text, submit)

        logger.debug(
            "input_executed",
            extra={
                "text_len": len(text),
                "submit": submit,
                "trigger": x_input.get("trigger") if isinstance(x_input, dict) else None,
            },
        )

        return PipelineResult.consumed()
