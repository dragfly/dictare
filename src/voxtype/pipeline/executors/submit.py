"""Submit executor.

Handles x_submit messages by calling the write function with submit action.
Messages with x_submit are consumed after execution.
Messages without x_submit pass through unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from voxtype.pipeline.base import PipelineResult

logger = logging.getLogger(__name__)


@dataclass
class SubmitExecutor:
    """Executor that handles submit actions.

    When a message has x_submit with enter=True, calls write_fn
    with the text and submit flag, then consumes the message.

    Attributes:
        write_fn: Callable that performs the actual text output.
                  Signature: write_fn(text: str, submit: bool) -> None
    """

    write_fn: Any  # Callable[[str, bool], None]

    @property
    def name(self) -> str:
        return "submit"

    @property
    def field(self) -> str:
        return "x_submit"

    def process(self, message: dict) -> PipelineResult:
        """Process message, executing submit if requested.

        Args:
            message: OpenVIP message dict.

        Returns:
            CONSUMED if submit executed, PASS otherwise.
        """
        x_submit = message.get("x_submit", {})
        if not x_submit:
            return PipelineResult.passed(message)

        enter = x_submit.get("enter", False) if isinstance(x_submit, dict) else bool(x_submit)
        text = message.get("text", "")

        self.write_fn(text, enter)

        logger.debug(
            "submit_executed",
            extra={
                "text_len": len(text),
                "enter": enter,
                "trigger": x_submit.get("trigger") if isinstance(x_submit, dict) else None,
            },
        )

        return PipelineResult.consumed()
