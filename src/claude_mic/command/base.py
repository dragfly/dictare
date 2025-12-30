"""Abstract base classes for voice command processing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

class CommandIntent(Enum):
    """Recognized voice command intents."""

    ASCOLTA = auto()       # Enter LISTENING mode
    SMETTI = auto()        # Exit LISTENING mode
    INCOLLA = auto()       # Paste from clipboard
    ANNULLA = auto()       # Undo (Ctrl+Z)
    RIPETI = auto()        # Repeat last transcription
    TARGET_WINDOW = auto() # Change target window
    TEXT = auto()          # Regular text to inject
    UNKNOWN = auto()       # Could not classify

@dataclass
class CommandResult:
    """Result of command interpretation."""

    intent: CommandIntent
    confidence: float  # 0.0 to 1.0
    original_text: str
    formatted_text: Optional[str] = None    # LLM-cleaned text
    target_query: Optional[str] = None      # For TARGET_WINDOW intent
    needs_clarification: bool = False       # True if user input needed
    clarification_options: list[str] = field(default_factory=list)

class IntentClassifier(ABC):
    """Abstract base class for intent classification."""

    @abstractmethod
    def classify(self, text: str) -> CommandResult:
        """Classify the intent of a voice command.

        Args:
            text: Transcribed text (with wake word already removed).

        Returns:
            Classification result with intent, confidence, and metadata.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this classifier is available.

        Returns:
            True if the classifier can be used.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the name of this classifier.

        Returns:
            Human-readable classifier name.
        """
        pass
