"""Input trigger detection filter.

Detects trigger words at the end of text that indicate the user
wants to submit/send the message. When detected, the trigger words
are removed and x_input is set with submit, trigger, and confidence.

Trigger words are organized by language. The filter checks triggers for:
1. Wildcard ("*") triggers -- always active regardless of language
2. The detected language of the message (from Whisper)

Pattern types:
- Multi-word: ["ok", "send"] - position-weighted confidence (closer to end = higher)
- Alternatives: ["ok|okay", "send|submit|invia"] - "|" means OR within each slot
- Last-word-only: ["go."] - word ending with "." triggers ONLY if it's the last word

Examples:
    "fix the parser bug ok send" -> "fix the parser bug" + x_input={submit: true, ...}
    "fix the bug go" -> "fix the bug" + x_input={submit: true, ...} (go. = last word only)
    "go check the code" -> unchanged (go is NOT the last word)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from dictare.pipeline.base import PipelineResult, fork_message
from dictare.pipeline.filters._text import (
    TriggerMatch,
    find_best_match,
    get_triggers_for_message,
)
from dictare.pipeline.filters._text import (
    tokenize as _tokenize,
)

logger = logging.getLogger(__name__)

# No hardcoded triggers -- configure in config.toml under [pipeline.submit_filter.triggers].
# Empty dict means no triggers active unless explicitly configured.
DEFAULT_SUBMIT_TRIGGERS: dict[str, list[list[str]]] = {}


@dataclass
class InputFilter:
    """Filter that detects input trigger words at the end of text.

    Uses position-weighted confidence: words closer to the end have higher weight.
    When a trigger is detected with sufficient confidence, the trigger words
    are removed from the text and x_input is set with submit action.

    Triggers are organized by language code. The filter checks:
    1. Wildcard ("*") triggers -- always active regardless of language
    2. Triggers for the message's detected language

    Use "*" for language-agnostic triggers that should work regardless of
    what language Whisper detects (e.g., English triggers when you speak
    multiple languages).

    Attributes:
        triggers: Dict mapping language codes (or "*") to trigger patterns.
        confidence_threshold: Minimum confidence to trigger submit (0.0-1.0).
        max_scan_words: Maximum words from end to scan for triggers.
        decay_rate: How fast confidence decays with position (0.95 = 5% per word).
    """

    triggers: dict[str, list[list[str]]] = field(
        default_factory=lambda: DEFAULT_SUBMIT_TRIGGERS
    )
    confidence_threshold: float = 0.85
    max_scan_words: int = 15
    decay_rate: float = 0.95

    @property
    def name(self) -> str:
        return "input_filter"

    def process(self, message: dict) -> PipelineResult:
        """Process message, detecting submit triggers.

        Args:
            message: OpenVIP message dict with 'text' field and optional 'language'.

        Returns:
            PipelineResult with potentially modified message.
        """
        text = message.get("text", "")
        if not text:
            return PipelineResult.passed(message)

        # Already has submit decision? Pass through
        x_input = message.get("x_input")
        if isinstance(x_input, dict) and "submit" in (x_input.get("ops") or []):
            return PipelineResult.passed(message)

        # Tokenize and scan for triggers
        tokens = _tokenize(text)
        if not tokens:
            return PipelineResult.passed(message)

        # Get triggers for this message's language
        active_triggers = get_triggers_for_message(self.triggers, message)
        if not active_triggers:
            return PipelineResult.passed(message)

        # Find best trigger match
        match = find_best_match(
            tokens, active_triggers, self.max_scan_words, self.decay_rate,
        )

        if match and match.confidence >= self.confidence_threshold:
            # Get matched tokens for logging
            matched_tokens = tokens[match.start_idx : match.end_idx + 1]

            # Log trigger detection (standard logging)
            logger.info(
                "submit_trigger",
                extra={
                    "pattern": match.pattern,
                    "matched_tokens": matched_tokens,
                    "confidence": match.confidence,
                },
            )

            # Remove trigger and everything after from original text
            cleaned_text = self._remove_trigger_from_text(text, match, tokens)

            # Create derived message with structured x_input
            new_message = fork_message(message, {
                "text": cleaned_text,
                "x_input": {
                    "ops": ["submit"],
                    "trigger": " ".join(matched_tokens),
                    "confidence": round(match.confidence, 3),
                    "source": "dictare/input-filter",
                },
            })

            return PipelineResult.augmented(new_message)

        return PipelineResult.passed(message)

    def _remove_trigger_from_text(
        self, text: str, match: TriggerMatch, tokens: list[str],
    ) -> str:
        """Remove trigger and everything after it from the original text.

        When a trigger is detected, everything from the FIRST trigger word
        to the END of the text is removed. The trigger word marks the start
        of a "command", not content.

        Args:
            text: Original text.
            match: The trigger match found.
            tokens: Normalized tokens.

        Returns:
            Text with trigger and everything after removed.
        """
        # Get the first trigger word (where to cut)
        first_trigger_token = tokens[match.start_idx]

        # Work with the original text, find words from the end
        # Split preserving whitespace info
        words = re.findall(r"\S+|\s+", text)

        # Find the position of the first trigger word (scanning from end)
        cut_position: int | None = None

        for i in range(len(words) - 1, -1, -1):
            word = words[i]
            if word.strip():  # Non-whitespace
                word_tokens = _tokenize(word)
                if first_trigger_token in word_tokens:
                    cut_position = i
                    break

        if cut_position is None:
            # Trigger not found in original text (shouldn't happen)
            return text

        # Keep everything BEFORE the trigger word
        result_words = words[:cut_position]

        # Join and clean up trailing whitespace
        result = "".join(result_words).rstrip()

        # If we removed everything, return empty string
        if not result.strip():
            return ""

        return result
