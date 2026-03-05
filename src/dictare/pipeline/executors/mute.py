"""Mute executor.

Handles x_mute messages by calling mute/unmute on the engine.
Messages with x_mute are consumed after execution.
Messages without x_mute pass through unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from dictare.pipeline.base import PipelineResult

logger = logging.getLogger(__name__)


@dataclass
class MuteExecutor:
    """Executor that handles voice mute/unmute commands.

    When a message has x_mute with action "mute", calls mute_fn.
    When a message has x_mute with action "unmute", calls unmute_fn.

    Attributes:
        mute_fn: Callable that mutes the engine. Signature: mute_fn() -> None
        unmute_fn: Callable that unmutes the engine. Signature: unmute_fn() -> None
    """

    mute_fn: Any  # Callable[[], None]
    unmute_fn: Any  # Callable[[], None]

    @property
    def name(self) -> str:
        return "mute"

    @property
    def field(self) -> str:
        return "x_mute"

    def process(self, message: dict) -> PipelineResult:
        """Process message, executing mute/unmute if requested.

        Args:
            message: OpenVIP message dict.

        Returns:
            CONSUMED if mute action executed, PASS otherwise.
        """
        x_mute = message.get("x_mute")
        if not x_mute or not isinstance(x_mute, dict):
            return PipelineResult.passed(message)

        action = x_mute.get("action")
        if action == "mute":
            self.mute_fn()
            logger.info(
                "mute_executed",
                extra={"trigger": x_mute.get("trigger")},
            )
        elif action == "unmute":
            self.unmute_fn()
            logger.info(
                "unmute_executed",
                extra={"trigger": x_mute.get("trigger")},
            )
        else:
            logger.warning("unknown_mute_action: %s", action)
            return PipelineResult.passed(message)

        return PipelineResult.consumed()
