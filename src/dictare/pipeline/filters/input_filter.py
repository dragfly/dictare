"""Input trigger detection filter.

Detects trigger words at the end of text that indicate the user
wants to submit/send the message. When detected, the trigger words
are removed and x_input is set with submit, trigger, and confidence.

Trigger words are organized by language. The filter checks triggers for:
1. Wildcard ("*") triggers — always active regardless of language
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
from dictare.pipeline.filters._text import normalize as _normalize
from dictare.pipeline.filters._text import tokenize as _tokenize

logger = logging.getLogger(__name__)

# No hardcoded triggers — configure in config.toml under [pipeline.submit_filter.triggers].
# Empty dict means no triggers active unless explicitly configured.
DEFAULT_SUBMIT_TRIGGERS: dict[str, list[list[str]]] = {}

@dataclass
class TriggerMatch:
    """A matched trigger pattern."""

    pattern: list[str]
    start_idx: int  # Index in token list where pattern starts
    end_idx: int  # Index in token list where pattern ends (exclusive)
    confidence: float

@dataclass
class InputFilter:
    """Filter that detects input trigger words at the end of text.

    Uses position-weighted confidence: words closer to the end have higher weight.
    When a trigger is detected with sufficient confidence, the trigger words
    are removed from the text and x_input is set with submit action.

    Triggers are organized by language code. The filter checks:
    1. Wildcard ("*") triggers — always active regardless of language
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

    def _get_triggers_for_message(self, message: dict) -> list[list[str]]:
        """Get combined trigger patterns for a message based on its language.

        Returns wildcard ("*") triggers plus language-specific triggers.
        Wildcard triggers come first (always active regardless of language).

        Args:
            message: OpenVIP message with optional 'language' field.

        Returns:
            Combined list of trigger patterns.
        """
        # Get message language, default to English
        lang = message.get("language", "en")

        # Normalize language code (e.g., "en-US" -> "en")
        if lang and "-" in lang:
            lang = lang.split("-")[0]
        lang = lang.lower() if lang else "en"

        combined: list[list[str]] = []

        # Always add wildcard triggers (language-agnostic)
        if "*" in self.triggers:
            combined.extend(self.triggers["*"])

        # Add language-specific triggers
        if lang != "*" and lang in self.triggers:
            combined.extend(self.triggers[lang])

        return combined

    def process(self, message: dict) -> PipelineResult:
        """Process message, detecting submit triggers.

        Checks triggers for the message's detected language plus English.

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
        active_triggers = self._get_triggers_for_message(message)
        if not active_triggers:
            return PipelineResult.passed(message)

        # Find best trigger match
        match = self._find_best_match(tokens, active_triggers)

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

    def _find_best_match(
        self, tokens: list[str], triggers: list[list[str]]
    ) -> TriggerMatch | None:
        """Find the best trigger match in tokens.

        Scans from the end of the token list, looking for trigger patterns.
        Returns the match with highest confidence.

        Args:
            tokens: Normalized tokens from text.
            triggers: List of trigger patterns to check.

        Returns:
            Best TriggerMatch or None if no match found.
        """
        if not tokens or not triggers:
            return None

        # Only scan last N tokens
        scan_tokens = tokens[-self.max_scan_words :]
        offset = len(tokens) - len(scan_tokens)

        best_match: TriggerMatch | None = None

        for pattern in triggers:
            # Check if any word in pattern has "." suffix (last-word-only marker)
            if any(w.endswith(".") for w in pattern):
                match = self._match_last_word_pattern(tokens, pattern)
            else:
                match = self._match_pattern(scan_tokens, pattern, offset)
            if match:
                if best_match is None or match.confidence > best_match.confidence:
                    best_match = match

        return best_match

    def _match_pattern(
        self, tokens: list[str], pattern: list[str], offset: int
    ) -> TriggerMatch | None:
        """Try to match a trigger pattern in tokens.

        Looks for pattern words appearing near the end.
        Handles non-consecutive matches (e.g., "ok ... invia" still matches "ok invia").

        Args:
            tokens: Tokens to search in.
            pattern: Pattern words to find.
            offset: Offset to add to indices for original token list.

        Returns:
            TriggerMatch if found, None otherwise.
        """
        if not pattern or not tokens:
            return None

        # Normalize pattern — each slot may have "|" alternatives (e.g. "ok|okay")
        pattern_norm = [
            [_normalize(alt) for alt in w.split("|")] for w in pattern
        ]

        # Find positions of each pattern word, searching from the end
        positions: list[int] = []
        search_start = len(tokens)

        for alternatives in reversed(pattern_norm):
            # Search backwards from current position
            found = False
            for i in range(search_start - 1, -1, -1):
                if tokens[i] in alternatives:
                    positions.append(i)
                    search_start = i  # Next word must be before this
                    found = True
                    break

            if not found:
                return None

        # Reverse to get original order
        positions.reverse()

        # Calculate confidence based on position of last word in pattern
        # Last word's position from end determines base confidence
        last_pos = positions[-1]
        distance_from_end = len(tokens) - 1 - last_pos
        base_confidence = self.decay_rate**distance_from_end

        # Bonus for consecutive words (full pattern match)
        is_consecutive = all(
            positions[i] + 1 == positions[i + 1] for i in range(len(positions) - 1)
        )
        if is_consecutive:
            # Full consecutive match gets confidence boost
            confidence = min(1.0, base_confidence * 1.1)
        else:
            # Non-consecutive gets slight penalty
            gap_penalty = 0.95 ** sum(
                positions[i + 1] - positions[i] - 1 for i in range(len(positions) - 1)
            )
            confidence = base_confidence * gap_penalty

        # Longer patterns get slight boost (more specific = more confident)
        if len(pattern) > 1:
            confidence = min(1.0, confidence * (1 + 0.02 * (len(pattern) - 1)))

        return TriggerMatch(
            pattern=pattern,
            start_idx=positions[0] + offset,
            end_idx=positions[-1] + offset + 1,
            confidence=confidence,
        )

    def _match_last_word_pattern(
        self, tokens: list[str], pattern: list[str]
    ) -> TriggerMatch | None:
        """Match a last-word-only pattern.

        Words ending with "." in the pattern must match the last token
        of the transcription. This is a binary check: matches or doesn't.

        For multi-word patterns, the "." word must be last in the text,
        and the other words must appear before it (like normal matching).

        Args:
            tokens: Full normalized token list from text.
            pattern: Pattern with at least one word ending in ".".

        Returns:
            TriggerMatch with confidence 1.0 if matched, None otherwise.
        """
        if not tokens or not pattern:
            return None

        # Strip "." marker and normalize — each slot may have "|" alternatives
        clean_pattern = [
            [_normalize(alt.rstrip(".")) for alt in w.split("|")] for w in pattern
        ]

        # The last word of the pattern (which has ".") must be the last token
        last_token = tokens[-1]
        if last_token not in clean_pattern[-1]:
            return None

        # Single-word pattern: just the last word check
        if len(clean_pattern) == 1:
            return TriggerMatch(
                pattern=pattern,
                start_idx=len(tokens) - 1,
                end_idx=len(tokens),
                confidence=1.0,
            )

        # Multi-word: other words must appear before the last token
        positions = [len(tokens) - 1]  # Last word already matched
        search_end = len(tokens) - 1

        for alternatives in reversed(clean_pattern[:-1]):
            found = False
            for i in range(search_end - 1, -1, -1):
                if tokens[i] in alternatives:
                    positions.append(i)
                    search_end = i
                    found = True
                    break
            if not found:
                return None

        positions.reverse()

        return TriggerMatch(
            pattern=pattern,
            start_idx=positions[0],
            end_idx=positions[-1] + 1,
            confidence=1.0,
        )

    def _remove_trigger_from_text(
        self, text: str, match: TriggerMatch, tokens: list[str]
    ) -> str:
        """Remove trigger and everything after it from the original text.

        When a trigger is detected, everything from the FIRST trigger word
        to the END of the text is removed. The trigger word marks the start
        of a "command", not content.

        Example:
            "ho un bug submit della frase" -> "ho un bug"
            "ok invia questo messaggio" -> "ok invia questo messaggio"
                (if "ok invia" is the trigger, but it's at the start)

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
