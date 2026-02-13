"""Agent switch detection filter.

Detects "agent <name>" or "agente <name>" at the end of text and
uses phonetic matching to find the best matching agent ID.

When detected, the trigger words are removed and x_agent_switch is set
to a structured object with target agent ID and confidence score.

Dynamic Agent List
------------------
The filter subscribes to the "agents.changed" event on the internal event bus.
When agents are added/removed, the filter automatically updates its list.

Examples:
    "fammi vedere il codice agent voxtype" -> "fammi vedere il codice" + x_agent_switch={target: "voxtype", ...}
    "questo bug agent koder" -> "questo bug" + x_agent_switch={target: "koder", ...} (even if heard as "coder")
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from voxtype.events import bus
from voxtype.pipeline.base import PipelineResult, derive_message

logger = logging.getLogger(__name__)

# Trigger words that precede agent name
AGENT_TRIGGERS = ["agent", "agente"]

def _normalize(text: str) -> str:
    """Normalize text for comparison.

    - Lowercase
    - Remove accents
    """
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text

def _tokenize(text: str) -> list[str]:
    """Split text into words, keeping only alphanumeric tokens."""
    return [w for w in re.split(r"[^a-zA-Z0-9]+", _normalize(text)) if w]

def _metaphone(word: str) -> str:
    """Compute the Metaphone phonetic code for a word.

    Pure Python implementation of Lawrence Philips' Metaphone algorithm.

    We avoid the ``jellyfish`` library because its Rust native extension
    (``_rustyfish.so``) causes Homebrew's ``install_name_tool`` to fail with
    "header too small" during ``brew install``.  Since we only call this on
    short agent names during occasional voice commands (not a hot path), the
    pure Python version has negligible performance difference.
    """
    if not word:
        return ""

    word = word.upper()
    word = "".join(c for c in word if c.isalpha())
    if not word:
        return ""

    # Drop first letter for silent-initial pairs
    if word[:2] in ("AE", "GN", "KN", "PN", "WR"):
        word = word[1:]
    if not word:
        return ""

    vowels = set("AEIOU")
    length = len(word)

    def _at(pos: int) -> str:
        return word[pos] if 0 <= pos < length else ""

    result: list[str] = []
    i = 0

    while i < length:
        c = word[i]

        # Skip duplicate adjacent letters (except C)
        if i > 0 and c == word[i - 1] and c != "C":
            i += 1
            continue

        if c in vowels:
            # Keep vowels only at the start of the word
            if i == 0:
                result.append(c)
            i += 1

        elif c == "B":
            # Silent B after M at end of word (DUMB → DM)
            if not (i == length - 1 and _at(i - 1) == "M"):
                result.append("B")
            i += 1

        elif c == "C":
            if _at(i + 1) == "I" and _at(i + 2) == "A":
                result.append("X")
                i += 3
            elif _at(i + 1) in ("E", "I", "Y"):
                result.append("S")
                i += 2
            elif _at(i + 1) == "H":
                # SCH → SK, otherwise CH → X
                result.append("K" if i > 0 and _at(i - 1) == "S" else "X")
                i += 2
            else:
                result.append("K")
                i += 1

        elif c == "D":
            if _at(i + 1) == "G" and _at(i + 2) in ("E", "I", "Y"):
                result.append("J")
                i += 3
            else:
                result.append("T")
                i += 1

        elif c == "F":
            result.append("F")
            i += 1

        elif c == "G":
            if _at(i + 1) == "H":
                if i + 2 < length and _at(i + 2) not in vowels:
                    i += 2  # GH before consonant → silent
                else:
                    result.append("K")
                    i += 2
            elif _at(i + 1) == "N":
                i += 1  # G before N → silent
            elif _at(i + 1) in ("E", "I", "Y"):
                result.append("J")
                i += 1
            else:
                result.append("K")
                i += 1

        elif c == "H":
            # Keep H only if before a vowel and not after a vowel
            if _at(i + 1) in vowels and _at(i - 1) not in vowels:
                result.append("H")
            i += 1

        elif c == "J":
            result.append("J")
            i += 1

        elif c == "K":
            # Silent K after C (already encoded by C → K)
            if i == 0 or _at(i - 1) != "C":
                result.append("K")
            i += 1

        elif c == "L":
            result.append("L")
            i += 1

        elif c == "M":
            result.append("M")
            i += 1

        elif c == "N":
            result.append("N")
            i += 1

        elif c == "P":
            if _at(i + 1) == "H":
                result.append("F")
                i += 2
            else:
                result.append("P")
                i += 1

        elif c == "Q":
            result.append("K")
            i += 1

        elif c == "R":
            result.append("R")
            i += 1

        elif c == "S":
            if _at(i + 1) == "H":
                result.append("X")
                i += 2
            elif _at(i + 1) == "I" and _at(i + 2) in ("A", "O"):
                result.append("X")
                i += 3
            else:
                result.append("S")
                i += 1

        elif c == "T":
            if _at(i + 1) == "H":
                result.append("0")  # θ
                i += 2
            elif _at(i + 1) == "I" and _at(i + 2) in ("A", "O"):
                result.append("X")
                i += 3
            else:
                result.append("T")
                i += 1

        elif c == "V":
            result.append("F")
            i += 1

        elif c == "W":
            if _at(i + 1) in vowels:
                result.append("W")
            i += 1

        elif c == "X":
            result.append("KS")
            i += 1

        elif c == "Y":
            if _at(i + 1) in vowels:
                result.append("Y")
            i += 1

        elif c == "Z":
            result.append("S")
            i += 1

        else:
            i += 1

    return "".join(result)

def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein (edit) distance between two strings.

    Pure Python implementation — see ``_metaphone`` docstring for why we
    avoid the ``jellyfish`` Rust extension.
    """
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if not s2:
        return len(s1)

    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(
                prev[j + 1] + 1,       # deletion
                curr[j] + 1,            # insertion
                prev[j] + (c1 != c2),   # substitution
            ))
        prev = curr
    return prev[-1]

def phonetic_score(word1: str, word2: str) -> float:
    """Calculate phonetic similarity score between two words.

    Uses Metaphone for phonetic comparison.

    Returns:
        Score between 0.0 and 1.0, where 1.0 means identical phonetic representation.
    """
    m1 = _metaphone(word1)
    m2 = _metaphone(word2)

    if m1 == m2:
        return 1.0

    # Partial match if one is prefix of the other
    if m1.startswith(m2) or m2.startswith(m1):
        return 0.7

    return 0.0

def edit_score(word1: str, word2: str) -> float:
    """Calculate normalized edit distance score.

    Returns:
        Score between 0.0 and 1.0, where 1.0 means identical strings.
    """
    if not word1 or not word2:
        return 0.0

    distance = _levenshtein_distance(word1, word2)
    max_len = max(len(word1), len(word2))
    return 1.0 - (distance / max_len)

def fuzzy_match_score(heard: str, agent_id: str) -> float:
    """Calculate combined fuzzy match score.

    Combines phonetic similarity (60%) with edit distance (40%).

    Args:
        heard: The word heard by STT.
        agent_id: The agent ID to match against.

    Returns:
        Score between 0.0 and 1.0.
    """
    heard_norm = _normalize(heard)
    agent_norm = _normalize(agent_id)

    p_score = phonetic_score(heard_norm, agent_norm)
    e_score = edit_score(heard_norm, agent_norm)

    # Weight phonetic higher since that's our main use case
    return 0.6 * p_score + 0.4 * e_score

@dataclass
class AgentMatch:
    """A matched agent."""

    agent_id: str
    heard_word: str
    score: float
    trigger_word: str  # "agent" or "agente"

@dataclass
class AgentFilter:
    """Filter that detects agent switch commands at the end of text.

    Looks for patterns like "agent <name>" or "agente <name>" and uses
    phonetic matching to find the best matching agent ID.

    Dynamic Updates
    ---------------
    If `subscribe_to_events=True` (default), the filter automatically
    subscribes to "agents.changed" events on the internal event bus.
    When agents are added/removed, the filter updates its list.

    Attributes:
        agent_ids: Initial list of agent IDs. Updated dynamically if subscribed.
        triggers: Words that trigger agent switch (default: ["agent", "agente"]).
        match_threshold: Minimum score to consider a match (0.0-1.0).
        max_scan_words: Maximum words from end to scan for triggers.
        subscribe_to_events: Whether to auto-subscribe to agents.changed events.
    """

    agent_ids: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=lambda: AGENT_TRIGGERS.copy())
    match_threshold: float = 0.5
    max_scan_words: int = 10
    subscribe_to_events: bool = True

    def __post_init__(self) -> None:
        """Subscribe to event bus after initialization."""
        if self.subscribe_to_events:
            bus.subscribe("agent.registered", self._on_agent_registered)
            bus.subscribe("agent.unregistered", self._on_agent_unregistered)
            logger.debug(
                "agent_filter_subscribed",
                extra={"events": ["agent.registered", "agent.unregistered"]},
            )

    def _on_agent_registered(self, agent_id: str) -> None:
        """Handle agent.registered event from event bus.

        Args:
            agent_id: ID of the registered agent.
        """
        if agent_id not in self.agent_ids:
            self.agent_ids.append(agent_id)
            logger.info(
                "agent_filter_agent_added",
                extra={"agent_id": agent_id, "agent_ids": self.agent_ids},
            )

    def _on_agent_unregistered(self, agent_id: str) -> None:
        """Handle agent.unregistered event from event bus.

        Args:
            agent_id: ID of the unregistered agent.
        """
        if agent_id in self.agent_ids:
            self.agent_ids.remove(agent_id)
            logger.info(
                "agent_filter_agent_removed",
                extra={"agent_id": agent_id, "agent_ids": self.agent_ids},
            )

    @property
    def name(self) -> str:
        return "agent_filter"

    def process(self, message: dict) -> PipelineResult:
        """Process message, detecting agent switch commands.

        Args:
            message: OpenVIP message dict with 'text' field.

        Returns:
            PipelineResult with potentially modified message.
        """
        text = message.get("text", "")
        if not text:
            return PipelineResult.passed(message)

        # Already has agent switch? Pass through
        if message.get("x_agent_switch"):
            return PipelineResult.passed(message)

        # No agents to match against
        if not self.agent_ids:
            return PipelineResult.passed(message)

        # Tokenize and scan for trigger pattern
        tokens = _tokenize(text)
        if len(tokens) < 2:  # Need at least "agent <name>"
            return PipelineResult.passed(message)

        # Find agent switch pattern
        match = self._find_agent_match(tokens)

        if match and match.score >= self.match_threshold:
            logger.info(
                "agent_switch",
                extra={
                    "heard": match.heard_word,
                    "matched": match.agent_id,
                    "score": match.score,
                    "trigger": match.trigger_word,
                },
            )

            # Get text before the trigger
            text_before = self._remove_pattern_from_text(text, match, tokens)

            # Build output messages
            output_messages = []

            # Message 1: text before trigger (if any) - sent to CURRENT agent
            if text_before.strip():
                msg_before = derive_message(message, {"text": text_before})
                # No x_agent_switch - goes to current agent
                output_messages.append(msg_before)

            # Message 2: empty text with switch flag - triggers switch, nothing sent
            switch_msg = derive_message(message, {
                "text": "",
                "x_agent_switch": {
                    "target": match.agent_id,
                    "confidence": round(match.score, 3),
                },
            })
            # Remove x_input - switch-only message doesn't need input behavior
            switch_msg.pop("x_input", None)
            output_messages.append(switch_msg)

            return PipelineResult.consumed(output_messages)

        return PipelineResult.passed(message)

    def _find_agent_match(self, tokens: list[str]) -> AgentMatch | None:
        """Find agent switch pattern in tokens.

        Looks for "agent <word>" near the end and matches <word>
        against known agent IDs using fuzzy matching.

        Trigger matching is exact (no fuzzy) - "agent" is a common word
        that Whisper recognizes reliably. Fuzzy matching is only used
        for agent IDs which can be arbitrary names.

        Args:
            tokens: Normalized tokens from text.

        Returns:
            AgentMatch if found, None otherwise.
        """
        # Normalize triggers once
        normalized_triggers = {_normalize(t): t for t in self.triggers}

        # Only scan last N tokens
        scan_start = max(0, len(tokens) - self.max_scan_words)
        scan_tokens = tokens[scan_start:]

        # Look for trigger word followed by potential agent name
        for i, token in enumerate(scan_tokens):
            # Exact match on trigger (no fuzzy - "agent" is well-recognized)
            if token in normalized_triggers:
                # Check if there's a word after the trigger
                if i + 1 < len(scan_tokens):
                    heard_word = scan_tokens[i + 1]

                    # Try to match against known agents (fuzzy match on ID)
                    best_match = self._match_agent(heard_word)
                    if best_match:
                        return AgentMatch(
                            agent_id=best_match[0],
                            heard_word=heard_word,
                            score=best_match[1],
                            trigger_word=normalized_triggers[token],
                        )

        return None

    def _match_agent(self, heard: str) -> tuple[str, float] | None:
        """Match heard word against known agent IDs.

        Args:
            heard: The word heard after "agent".

        Returns:
            Tuple of (agent_id, score) for best match, or None.
        """
        best_agent = None
        best_score = 0.0

        for agent_id in self.agent_ids:
            score = fuzzy_match_score(heard, agent_id)
            if score > best_score:
                best_agent = agent_id
                best_score = score

        if best_agent and best_score >= self.match_threshold:
            return (best_agent, best_score)

        return None

    def _remove_pattern_from_text(
        self, text: str, match: AgentMatch, tokens: list[str]
    ) -> str:
        """Remove the trigger and everything after from original text.

        When user says "agent voxtype", we remove "agent voxtype" and
        anything after it. This handles cases where Whisper splits
        the agent name (e.g., "voxtype" -> "Fox type").

        Args:
            text: Original text.
            match: The agent match found.
            tokens: Normalized tokens.

        Returns:
            Text with trigger pattern and everything after removed.
        """
        # Find trigger word and remove everything from it to the end
        # This handles multi-word transcriptions like "Fox type" for "voxtype"
        pattern = rf"\b{match.trigger_word}\b.*$"
        cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE).rstrip()

        return cleaned
