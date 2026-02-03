"""Submit trigger detection filter.

Detects trigger words at the end of text that indicate the user
wants to submit/send the message. When detected, the trigger words
are removed and x_submit is set to true.

Trigger words are organized by language. The filter checks triggers for:
1. The detected language of the message (from Whisper)
2. English (always, as a lingua franca)

Examples:
    "ho un bug nel parser ok invia" -> "ho un bug nel parser" + x_submit=true
    "fammi vedere il codice submit" -> "fammi vedere il codice" + x_submit=true
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from voxtype.pipeline.base import FilterResult

logger = logging.getLogger(__name__)

# Default trigger word patterns organized by language
# Each language has a list of patterns (each pattern is a list of words)
# Order matters: longer/more specific patterns should come first
DEFAULT_SUBMIT_TRIGGERS: dict[str, list[list[str]]] = {
    "it": [
        # Multi-word (higher priority) - these are explicit submit commands
        ["ok", "invia"],
        ["ok", "in", "via"],  # "invia" often heard as "in via"
        ["ok", "manda"],
        ["ok", "fatto"],
        ["va", "bene", "invia"],
        ["va", "bene", "in", "via"],
        ["invia", "adesso"],
        ["manda", "adesso"],
        # Single word - only explicit submit words
        ["invia"],
        ["in", "via"],  # "invia" often heard as "in via"
        ["manda"],
        # NOTE: "fatto" and "adesso" removed - too common, caused false positives
    ],
    "en": [
        # Multi-word (higher priority)
        ["ok", "send"],
        ["ok", "submit"],
        ["go", "ahead"],
        # Single word - only explicit submit words
        ["submit"],
        ["send"],
        # NOTE: "go" removed - too common, caused false positives
    ],
    "es": [
        ["ok", "enviar"],
        ["enviar"],
        ["envía"],
        ["listo"],
    ],
    "de": [
        ["ok", "senden"],
        ["senden"],
        ["abschicken"],
        ["fertig"],
    ],
    "fr": [
        ["ok", "envoyer"],
        ["envoyer"],
        ["envoie"],
        ["terminé"],
    ],
}

def _normalize(text: str) -> str:
    """Normalize text for comparison.

    - Lowercase
    - Remove accents
    - Collapse whitespace
    """
    # Lowercase
    text = text.lower()
    # Remove accents (NFD decomposition, strip combining chars)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text

def _tokenize(text: str) -> list[str]:
    """Split text into words, keeping only alphanumeric tokens."""
    # Split on non-alphanumeric, filter empty
    return [w for w in re.split(r"[^a-zA-Z0-9]+", _normalize(text)) if w]

@dataclass
class TriggerMatch:
    """A matched trigger pattern."""

    pattern: list[str]
    start_idx: int  # Index in token list where pattern starts
    end_idx: int  # Index in token list where pattern ends (exclusive)
    confidence: float

@dataclass
class SubmitFilter:
    """Filter that detects submit trigger words at the end of text.

    Uses position-weighted confidence: words closer to the end have higher weight.
    When a trigger is detected with sufficient confidence, the trigger words
    are removed from the text and x_submit is set to true.

    Triggers are organized by language code. The filter checks:
    1. Triggers for the message's detected language
    2. English triggers (always, as lingua franca)

    Attributes:
        triggers: Dict mapping language codes to trigger patterns.
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
        return "submit_filter"

    def _get_triggers_for_message(self, message: dict) -> list[list[str]]:
        """Get combined trigger patterns for a message based on its language.

        Returns triggers for the message's language plus English (always).
        Language-specific triggers come first (higher priority).

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

        # Add language-specific triggers first (higher priority)
        if lang in self.triggers:
            combined.extend(self.triggers[lang])

        # Always add English triggers (lingua franca)
        if lang != "en" and "en" in self.triggers:
            combined.extend(self.triggers["en"])

        return combined

    def process(self, message: dict) -> FilterResult:
        """Process message, detecting submit triggers.

        Checks triggers for the message's detected language plus English.

        Args:
            message: OpenVIP message dict with 'text' field and optional 'language'.

        Returns:
            FilterResult with potentially modified message.
        """
        text = message.get("text", "")
        if not text:
            return FilterResult.passed(message)

        # Already has submit flag? Pass through
        if message.get("x_submit"):
            return FilterResult.passed(message)

        # Tokenize and scan for triggers
        tokens = _tokenize(text)
        if not tokens:
            return FilterResult.passed(message)

        # Get triggers for this message's language
        active_triggers = self._get_triggers_for_message(message)
        if not active_triggers:
            return FilterResult.passed(message)

        # Find best trigger match
        match = self._find_best_match(tokens, active_triggers)

        if match and match.confidence >= self.confidence_threshold:
            # Log trigger detection
            matched_tokens = tokens[match.start_idx : match.end_idx]
            logger.info(
                "submit_trigger",
                extra={
                    "pattern": match.pattern,
                    "matched_tokens": matched_tokens,
                    "confidence": match.confidence,
                },
            )

            # Remove trigger words from original text
            cleaned_text = self._remove_trigger_from_text(text, match, tokens)

            # Create new message with submit flag
            new_message = message.copy()
            new_message["text"] = cleaned_text
            new_message["x_submit"] = True

            # Remove visual_newline if present (submit takes precedence)
            new_message.pop("x_visual_newline", None)

            return FilterResult.augmented(new_message)

        return FilterResult.passed(message)

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

        # Normalize pattern
        pattern_norm = [_normalize(w) for w in pattern]

        # Find positions of each pattern word, searching from the end
        positions: list[int] = []
        search_start = len(tokens)

        for word in reversed(pattern_norm):
            # Search backwards from current position
            found = False
            for i in range(search_start - 1, -1, -1):
                if tokens[i] == word:
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

    def _remove_trigger_from_text(
        self, text: str, match: TriggerMatch, tokens: list[str]
    ) -> str:
        """Remove matched trigger words from the original text.

        This is tricky because we need to map normalized tokens back to
        the original text. We use a simple approach: find and remove
        the matched words from the end of the text.

        Args:
            text: Original text.
            match: The trigger match found.
            tokens: Normalized tokens.

        Returns:
            Text with trigger words removed.
        """
        # Get the trigger words we need to remove
        trigger_tokens = set(tokens[match.start_idx : match.end_idx])

        # Work with the original text, find words from the end
        # Split preserving whitespace info
        words = re.findall(r"\S+|\s+", text)

        # Find which word segments to remove (from the end)
        to_remove: set[int] = set()
        remaining_triggers = trigger_tokens.copy()

        # Scan from end
        for i in range(len(words) - 1, -1, -1):
            word = words[i]
            if word.strip():  # Non-whitespace
                # Check if this word contains any trigger token
                word_tokens = _tokenize(word)
                for wt in word_tokens:
                    if wt in remaining_triggers:
                        to_remove.add(i)
                        remaining_triggers.discard(wt)
                        break

            if not remaining_triggers:
                break

        # Remove marked words and trailing whitespace
        result_words = [w for i, w in enumerate(words) if i not in to_remove]

        # Join and clean up trailing whitespace
        result = "".join(result_words).rstrip()

        # If we removed everything, return empty string
        if not result.strip():
            return ""

        return result
