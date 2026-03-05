"""Shared text normalization and pattern matching for pipeline filters."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> str:
    """Normalize text for comparison.

    - Lowercase
    - Remove accents (NFD decomposition, strip combining chars)
    """
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


def tokenize(text: str) -> list[str]:
    """Split text into words, keeping only alphanumeric tokens."""
    return [w for w in re.split(r"[^a-zA-Z0-9]+", normalize(text)) if w]


@dataclass
class TriggerMatch:
    """A matched trigger pattern."""

    pattern: list[str]
    start_idx: int  # Index in token list where pattern starts
    end_idx: int  # Index in token list where pattern ends (exclusive)
    confidence: float


def get_triggers_for_message(
    triggers: dict[str, list[list[str]]], message: dict,
) -> list[list[str]]:
    """Get combined trigger patterns for a message based on its language.

    Returns wildcard ("*") triggers plus language-specific triggers.
    """
    lang = message.get("language", "en")
    if lang and "-" in lang:
        lang = lang.split("-")[0]
    lang = lang.lower() if lang else "en"

    combined: list[list[str]] = []
    if "*" in triggers:
        combined.extend(triggers["*"])
    if lang != "*" and lang in triggers:
        combined.extend(triggers[lang])
    return combined


def match_pattern(
    tokens: list[str],
    pattern: list[str],
    offset: int,
    decay_rate: float = 0.95,
) -> TriggerMatch | None:
    """Try to match a trigger pattern in tokens.

    Looks for pattern words appearing near the end.
    Handles non-consecutive matches (e.g., "ok ... invia" still matches).

    Args:
        tokens: Tokens to search in (windowed slice).
        pattern: Pattern words to find.
        offset: Offset to add to indices for original token list.
        decay_rate: Confidence decay rate per word from end.

    Returns:
        TriggerMatch if found, None otherwise.
    """
    if not pattern or not tokens:
        return None

    # Normalize pattern -- each slot may have "|" alternatives
    pattern_norm = [
        [normalize(alt) for alt in w.split("|")] for w in pattern
    ]

    # Find positions of each pattern word, searching from the end
    positions: list[int] = []
    search_start = len(tokens)

    for alternatives in reversed(pattern_norm):
        found = False
        for i in range(search_start - 1, -1, -1):
            if tokens[i] in alternatives:
                positions.append(i)
                search_start = i
                found = True
                break
        if not found:
            return None

    positions.reverse()

    # Calculate confidence based on position of last word
    last_pos = positions[-1]
    distance_from_end = len(tokens) - 1 - last_pos
    base_confidence = decay_rate**distance_from_end

    is_consecutive = all(
        positions[i] + 1 == positions[i + 1] for i in range(len(positions) - 1)
    )
    if is_consecutive:
        confidence = min(1.0, base_confidence * 1.1)
    else:
        gap_penalty = 0.95 ** sum(
            positions[i + 1] - positions[i] - 1 for i in range(len(positions) - 1)
        )
        confidence = base_confidence * gap_penalty

    if len(pattern) > 1:
        confidence = min(1.0, confidence * (1 + 0.02 * (len(pattern) - 1)))

    return TriggerMatch(
        pattern=pattern,
        start_idx=positions[0] + offset,
        end_idx=positions[-1] + offset + 1,
        confidence=confidence,
    )


def match_last_word_pattern(
    tokens: list[str], pattern: list[str],
) -> TriggerMatch | None:
    """Match a last-word-only pattern.

    Words ending with "." in the pattern must match the last token.
    """
    if not tokens or not pattern:
        return None

    clean_pattern = [
        [normalize(alt.rstrip(".")) for alt in w.split("|")] for w in pattern
    ]

    last_token = tokens[-1]
    if last_token not in clean_pattern[-1]:
        return None

    if len(clean_pattern) == 1:
        return TriggerMatch(
            pattern=pattern,
            start_idx=len(tokens) - 1,
            end_idx=len(tokens),
            confidence=1.0,
        )

    positions = [len(tokens) - 1]
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


def find_best_match(
    tokens: list[str],
    triggers: list[list[str]],
    max_scan_words: int = 15,
    decay_rate: float = 0.95,
) -> TriggerMatch | None:
    """Find the best trigger match in tokens.

    Scans from the end of the token list. Returns the match with highest
    confidence.
    """
    if not tokens or not triggers:
        return None

    scan_tokens = tokens[-max_scan_words:]
    offset = len(tokens) - len(scan_tokens)

    best_match: TriggerMatch | None = None

    for pattern in triggers:
        if any(w.endswith(".") for w in pattern):
            m = match_last_word_pattern(tokens, pattern)
        else:
            m = match_pattern(scan_tokens, pattern, offset, decay_rate)
        if m:
            if best_match is None or m.confidence > best_match.confidence:
                best_match = m

    return best_match
