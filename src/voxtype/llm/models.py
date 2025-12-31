"""Data models for LLM-first processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Import AppState from core to avoid duplication
from voxtype.core.state import AppState

class Action(Enum):
    """Actions the LLM can decide."""

    IGNORE = "ignore"  # No trigger phrase, noise, etc.
    INJECT = "inject"  # Inject text into terminal
    CHANGE_STATE = "change_state"  # Enter/exit LISTENING mode
    EXECUTE = "execute"  # Execute command (repeat)

class Command(Enum):
    """Executable commands."""

    REPEAT = "repeat"

@dataclass
class LLMRequest:
    """Request to the LLM processor."""

    text: str
    current_state: AppState
    trigger_phrase: str | None = None
    history: list[str] = field(default_factory=list)

@dataclass
class LLMResponse:
    """Response from the LLM processor."""

    action: Action
    new_state: AppState | None = None
    text_to_inject: str | None = None
    command: Command | None = None
    command_args: dict[str, Any] | None = None
    user_feedback: str | None = None
    confidence: float = 1.0
    # Debug info for structured logging
    backend: str = "unknown"  # "ollama" or "keyword"
    override_reason: str | None = None  # Why LLM decision was overridden
    raw_llm_response: str | None = None  # Raw LLM JSON for debugging

    @classmethod
    def ignore(cls, reason: str = "", backend: str = "keyword") -> LLMResponse:
        """Create an IGNORE response."""
        return cls(action=Action.IGNORE, user_feedback=reason, backend=backend)

    @classmethod
    def inject(cls, text: str, backend: str = "keyword", override: str | None = None) -> LLMResponse:
        """Create an INJECT response."""
        return cls(action=Action.INJECT, text_to_inject=text, backend=backend, override_reason=override)

    @classmethod
    def enter_listening(cls, backend: str = "keyword") -> LLMResponse:
        """Create a response to enter LISTENING mode."""
        return cls(
            action=Action.CHANGE_STATE,
            new_state=AppState.LISTENING,
            user_feedback="Listening mode activated",
            backend=backend,
        )

    @classmethod
    def exit_listening(cls, backend: str = "keyword") -> LLMResponse:
        """Create a response to exit LISTENING mode."""
        return cls(
            action=Action.CHANGE_STATE,
            new_state=AppState.IDLE,
            user_feedback="Listening mode deactivated",
            backend=backend,
        )

    @classmethod
    def execute(cls, command: Command, args: dict[str, Any] | None = None, backend: str = "keyword") -> LLMResponse:
        """Create an EXECUTE response."""
        return cls(action=Action.EXECUTE, command=command, command_args=args, backend=backend)
