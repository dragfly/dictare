"""Base classes for the OpenVIP pipeline.

The pipeline processes messages through a chain of steps (filters or executors).
Each step can pass, augment, or consume messages. The same Pipeline class is
used for both filter and executor pipelines — the mechanism is identical.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

class PipelineAction(StrEnum):
    """Action taken by a pipeline step on a message."""

    PASS = "pass"  # Message continues unchanged
    AUGMENT = "augment"  # Message modified (metadata added, text changed)
    CONSUME = "consume"  # Message stopped, step handles it

@dataclass
class PipelineResult:
    """Result of processing a message through a pipeline step.

    Attributes:
        action: What the step did with the message.
        messages: Output messages (0, 1, or more). Empty if consumed without output.
    """

    action: PipelineAction
    messages: list[dict] = field(default_factory=list)

    @classmethod
    def passed(cls, message: dict) -> PipelineResult:
        """Message passes through unchanged."""
        return cls(action=PipelineAction.PASS, messages=[message])

    @classmethod
    def augmented(cls, message: dict) -> PipelineResult:
        """Message was modified (new ID expected)."""
        return cls(action=PipelineAction.AUGMENT, messages=[message])

    @classmethod
    def consumed(cls, messages: list[dict] | None = None) -> PipelineResult:
        """Message was consumed. Optionally emit new messages."""
        return cls(action=PipelineAction.CONSUME, messages=messages or [])

class Filter(Protocol):
    """Protocol for pipeline filters.

    Filters process messages and can pass, augment, or consume them.
    Implementations should be stateless or thread-safe if stateful.
    """

    @property
    def name(self) -> str:
        """Filter name for logging and configuration."""
        ...

    def process(self, message: dict) -> PipelineResult:
        """Process a message.

        Args:
            message: OpenVIP message dict with at least 'text' field.

        Returns:
            PipelineResult indicating action and output messages.
        """
        ...

class Executor(Protocol):
    """Protocol for pipeline executors.

    Executors act on structured x_ fields produced by filters.
    Each executor handles exactly one x_ field (1:1 mapping).
    The field property is metadata for introspection — skip logic
    lives inside process() (return PASS if field is absent).

    Dependencies are injected at construction time.
    """

    @property
    def name(self) -> str:
        """Executor name for logging and configuration."""
        ...

    @property
    def field(self) -> str:
        """The single x_ field this executor handles."""
        ...

    def process(self, message: dict) -> PipelineResult:
        """Process a message.

        Args:
            message: OpenVIP message dict.

        Returns:
            PipelineResult indicating action and output messages.
        """
        ...

def fork_message(original: dict, changes: dict | None = None) -> dict:
    """Create a forked message with new ID and tracing fields.

    Handles the ID triad automatically:
    - New unique id
    - trace_id = original's trace_id (or original's id if absent)
    - parent_id = original's id

    Args:
        original: The source message to derive from.
        changes: Optional dict of fields to merge into the new message.

    Returns:
        New message dict with updated ID triad and merged changes.
    """
    msg = original.copy()
    original_id = msg.get("id", str(uuid.uuid4()))
    msg["id"] = str(uuid.uuid4())
    msg["trace_id"] = original.get("trace_id", original_id)
    msg["parent_id"] = original_id
    if changes:
        msg.update(changes)
    return msg

class Pipeline:
    """Executes a chain of steps on messages.

    Steps are executed in order. If a step consumes a message,
    subsequent steps are not called for that message, but any
    output messages from the consuming step are processed through
    the remaining steps.

    The same class is used for filter pipelines and executor pipelines.
    """

    def __init__(self, steps: list[Filter | Executor] | None = None) -> None:
        """Initialize pipeline with steps.

        Args:
            steps: List of filters or executors to apply, in order.
        """
        self._steps: list[Filter | Executor] = steps or []

    def add_step(self, step: Filter | Executor) -> None:
        """Add a step to the end of the pipeline."""
        self._steps.append(step)

    def process(self, message: dict) -> list[dict]:
        """Process a message through all steps.

        Args:
            message: OpenVIP message dict.

        Returns:
            List of output messages (may be 0, 1, or more).
        """
        messages = [message]

        for step in self._steps:
            next_messages = []

            for msg in messages:
                result = step.process(msg)
                next_messages.extend(result.messages)

            messages = next_messages

            if not messages:
                break

        return messages

    def process_many(self, messages: list[dict]) -> list[dict]:
        """Process multiple messages through all steps.

        Convenience method for running a list of messages (e.g., output
        from a filter pipeline) through an executor pipeline.

        Args:
            messages: List of OpenVIP message dicts.

        Returns:
            Combined list of output messages from all inputs.
        """
        output = []
        for msg in messages:
            output.extend(self.process(msg))
        return output

    @property
    def step_names(self) -> list[str]:
        """Names of steps in the pipeline."""
        return [s.name for s in self._steps]

    def __len__(self) -> int:
        return len(self._steps)

    def __repr__(self) -> str:
        return f"Pipeline(steps={self.step_names})"
