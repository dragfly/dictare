"""Agent switch executor.

Handles x_agent_switch messages by switching the engine's current agent.
Messages with x_agent_switch are consumed (not forwarded to agents).
Messages without x_agent_switch pass through unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dictare.pipeline.base import PipelineResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class AgentSwitchExecutor:
    """Executor that handles agent switch commands.

    When a message has x_agent_switch, calls the switch function
    and consumes the message. Messages without x_agent_switch
    pass through unchanged.

    Attributes:
        switch_fn: Callable that performs the actual agent switch.
                   Signature: switch_fn(agent_name: str) -> bool
    """

    switch_fn: Any  # Callable[[str], bool]

    @property
    def name(self) -> str:
        return "agent_switch"

    @property
    def field(self) -> str:
        return "x_agent_switch"

    def process(self, message: dict) -> PipelineResult:
        """Process message, executing agent switch if requested.

        Args:
            message: OpenVIP message dict.

        Returns:
            CONSUMED if switch executed, PASS otherwise.
        """
        x_switch = message.get("x_agent_switch", {})
        if not x_switch:
            return PipelineResult.passed(message)

        target = x_switch.get("target") if isinstance(x_switch, dict) else None
        if not target:
            return PipelineResult.passed(message)

        success = self.switch_fn(target)
        if success:
            logger.info(
                "agent_switch_executed",
                extra={"target": target, "confidence": x_switch.get("confidence")},
            )
        else:
            logger.warning(
                "agent_switch_failed",
                extra={"target": target},
            )

        # Always consume switch messages — they're commands, not content
        return PipelineResult.consumed()
