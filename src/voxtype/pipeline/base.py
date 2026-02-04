"""Base classes for the pipeline filter system.

The pipeline processes OpenVIP messages through a chain of filters.
Each filter can pass, augment, or consume messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

class FilterAction(str, Enum):
    """Action taken by a filter on a message."""

    PASS = "pass"  # Message continues unchanged
    AUGMENT = "augment"  # Message modified (metadata added, text changed)
    CONSUME = "consume"  # Message stopped, filter handles it

@dataclass
class FilterResult:
    """Result of processing a message through a filter.

    Attributes:
        action: What the filter did with the message.
        messages: Output messages (0, 1, or more). Empty if consumed without output.
    """

    action: FilterAction
    messages: list[dict] = field(default_factory=list)

    @classmethod
    def passed(cls, message: dict) -> FilterResult:
        """Message passes through unchanged."""
        return cls(action=FilterAction.PASS, messages=[message])

    @classmethod
    def augmented(cls, message: dict) -> FilterResult:
        """Message was modified."""
        return cls(action=FilterAction.AUGMENT, messages=[message])

    @classmethod
    def consumed(cls, messages: list[dict] | None = None) -> FilterResult:
        """Message was consumed. Optionally emit different messages."""
        return cls(action=FilterAction.CONSUME, messages=messages or [])

class Filter(Protocol):
    """Protocol for pipeline filters.

    Filters process messages and can pass, augment, or consume them.
    Implementations should be stateless or thread-safe if stateful.
    """

    @property
    def name(self) -> str:
        """Filter name for logging and configuration."""
        ...

    def process(self, message: dict) -> FilterResult:
        """Process a message.

        Args:
            message: OpenVIP message dict with at least 'text' field.

        Returns:
            FilterResult indicating action and output messages.
        """
        ...

class Pipeline:
    """Executes a chain of filters on messages.

    Filters are executed in order. If a filter consumes a message,
    subsequent filters are not called for that message, but any
    output messages from the consuming filter are processed through
    the remaining filters.
    """

    def __init__(self, filters: list[Filter] | None = None) -> None:
        """Initialize pipeline with filters.

        Args:
            filters: List of filters to apply, in order.
        """
        self._filters = filters or []

    def add_filter(self, filter_: Filter) -> None:
        """Add a filter to the end of the pipeline."""
        self._filters.append(filter_)

    def process(self, message: dict) -> list[dict]:
        """Process a message through all filters.

        Args:
            message: OpenVIP message dict.

        Returns:
            List of output messages (may be 0, 1, or more).
        """
        messages = [message]

        for filter_ in self._filters:
            next_messages = []

            for msg in messages:
                result = filter_.process(msg)

                if result.action == FilterAction.CONSUME:
                    # Filter consumed the message
                    # Any output messages continue through remaining filters
                    next_messages.extend(result.messages)
                else:
                    # PASS or AUGMENT - message continues
                    next_messages.extend(result.messages)

            messages = next_messages

            # If no messages left, stop early
            if not messages:
                break

        return messages

    @property
    def filter_names(self) -> list[str]:
        """Names of filters in the pipeline."""
        return [f.name for f in self._filters]

    def __len__(self) -> int:
        return len(self._filters)

    def __repr__(self) -> str:
        return f"Pipeline(filters={self.filter_names})"
