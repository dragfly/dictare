"""Keyword-based intent classification (fallback)."""

from __future__ import annotations

import re
from typing import ClassVar

from claude_mic.command.base import (
    CommandIntent,
    CommandResult,
    IntentClassifier,
)


class KeywordClassifier(IntentClassifier):
    """Simple keyword-based intent classifier.

    Used as fallback when Ollama is unavailable.
    Supports Italian and English keywords with basic fuzzy matching.
    """

    # Keywords mapped to intents (supports variations)
    KEYWORDS: ClassVar[dict[CommandIntent, list[str]]] = {
        CommandIntent.ASCOLTA: [
            "ascolta", "ascolto", "ascoltami",
            "listen", "listening", "start listening",
        ],
        CommandIntent.SMETTI: [
            "smetti", "stop", "basta", "ferma", "fermati",
            "smetti di ascoltare", "stop listening",
        ],
        CommandIntent.INCOLLA: [
            "incolla", "paste", "inserisci",
        ],
        CommandIntent.ANNULLA: [
            "annulla", "undo", "cancella", "elimina",
        ],
        CommandIntent.RIPETI: [
            "ripeti", "repeat", "ancora", "ridici", "di nuovo",
        ],
        CommandIntent.TARGET_WINDOW: [
            "invia a", "invia al", "manda a", "manda al",
            "target", "focus", "finestra",
            "send to", "switch to",
        ],
    }

    # Patterns for extracting target from window commands
    WINDOW_PATTERNS: ClassVar[list[str]] = [
        r"(?:invia|manda)\s+(?:a|al|alla)\s+(.+)",
        r"(?:target|focus)\s+(?:su|on)?\s*(.+)",
        r"(?:send|switch)\s+to\s+(.+)",
        r"finestra\s+(.+)",
    ]

    def classify(self, text: str) -> CommandResult:
        """Classify using keyword matching."""
        text_lower = text.lower().strip()
        words = text_lower.split()

        if not words:
            return CommandResult(
                intent=CommandIntent.UNKNOWN,
                confidence=0.0,
                original_text=text,
            )

        # Check for target window commands first (they have patterns)
        target_query = self._extract_window_target(text_lower)
        if target_query:
            return CommandResult(
                intent=CommandIntent.TARGET_WINDOW,
                confidence=0.85,
                original_text=text,
                target_query=target_query,
            )

        # Check against keyword lists
        for intent, keywords in self.KEYWORDS.items():
            if intent == CommandIntent.TARGET_WINDOW:
                continue  # Already handled above

            for keyword in keywords:
                # Exact match at start
                if text_lower.startswith(keyword):
                    return CommandResult(
                        intent=intent,
                        confidence=0.95,
                        original_text=text,
                    )

                # Single word exact match
                if len(keyword.split()) == 1 and words[0] == keyword:
                    return CommandResult(
                        intent=intent,
                        confidence=0.95,
                        original_text=text,
                    )

                # Fuzzy match for first word (handle typos)
                if len(keyword.split()) == 1 and self._fuzzy_match(words[0], keyword):
                    return CommandResult(
                        intent=intent,
                        confidence=0.70,
                        original_text=text,
                    )

        # No command matched - treat as regular text
        return CommandResult(
            intent=CommandIntent.TEXT,
            confidence=1.0,
            original_text=text,
            formatted_text=text,
        )

    def _extract_window_target(self, text: str) -> str | None:
        """Extract target window name from command."""
        for pattern in self.WINDOW_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _fuzzy_match(self, s1: str, s2: str, max_distance: int = 2) -> bool:
        """Check if strings are similar (simple Levenshtein approximation)."""
        if abs(len(s1) - len(s2)) > max_distance:
            return False

        # For short strings, require exact match
        if len(s1) < 4 or len(s2) < 4:
            return s1 == s2

        # Check prefix match (first 3 chars must match)
        if s1[:3] != s2[:3]:
            return False

        # Count differences
        differences = sum(1 for a, b in zip(s1, s2) if a != b)
        differences += abs(len(s1) - len(s2))

        return differences <= max_distance

    def is_available(self) -> bool:
        """Keyword classifier is always available."""
        return True

    def get_name(self) -> str:
        """Get classifier name."""
        return "keyword"
