"""Data models for LLM-first processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class AppState(Enum):
    """Application state."""

    IDLE = "idle"
    LISTENING = "listening"

class Action(Enum):
    """Actions the LLM can decide."""

    IGNORE = "ignore"  # No trigger phrase, noise, etc.
    INJECT = "inject"  # Inject text into terminal
    CHANGE_STATE = "change_state"  # Enter/exit LISTENING mode
    EXECUTE = "execute"  # Execute command (paste, undo, repeat)

class Command(Enum):
    """Executable commands."""

    PASTE = "paste"
    UNDO = "undo"
    REPEAT = "repeat"
    TARGET_WINDOW = "target_window"

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

    @classmethod
    def ignore(cls, reason: str = "") -> LLMResponse:
        """Create an IGNORE response."""
        return cls(action=Action.IGNORE, user_feedback=reason)

    @classmethod
    def inject(cls, text: str) -> LLMResponse:
        """Create an INJECT response."""
        return cls(action=Action.INJECT, text_to_inject=text)

    @classmethod
    def enter_listening(cls) -> LLMResponse:
        """Create a response to enter LISTENING mode."""
        return cls(
            action=Action.CHANGE_STATE,
            new_state=AppState.LISTENING,
            user_feedback="Modalita ascolto attivata",
        )

    @classmethod
    def exit_listening(cls) -> LLMResponse:
        """Create a response to exit LISTENING mode."""
        return cls(
            action=Action.CHANGE_STATE,
            new_state=AppState.IDLE,
            user_feedback="Modalita ascolto disattivata",
        )

    @classmethod
    def execute(cls, command: Command, args: dict[str, Any] | None = None) -> LLMResponse:
        """Create an EXECUTE response."""
        return cls(action=Action.EXECUTE, command=command, command_args=args)
