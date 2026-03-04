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
    "show me the code agent dictare" -> "show me the code" + x_agent_switch={target: "dictare", ...}
    "this bug agent koder" -> "this bug" + x_agent_switch={target: "koder", ...} (even if heard as "coder")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from dictare.core.agent_manager import AgentManager
from dictare.core.bus import bus
from dictare.pipeline.base import PipelineResult, fork_message
from dictare.pipeline.filters._text import normalize as _normalize
from dictare.pipeline.filters._text import tokenize as _tokenize
from dictare.utils.jellyfish import levenshtein_distance, metaphone

logger = logging.getLogger(__name__)

# Trigger words that precede agent name
AGENT_TRIGGERS = ["agent", "agente"]

def phonetic_score(word1: str, word2: str) -> float:
    """Calculate phonetic similarity score between two words.

    Uses Metaphone for phonetic comparison.

    Returns:
        Score between 0.0 and 1.0, where 1.0 means identical phonetic representation.
    """
    m1 = metaphone(word1)
    m2 = metaphone(word2)

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

    distance = levenshtein_distance(word1, word2)
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
        if agent_id in AgentManager.RESERVED_AGENT_IDS:
            return
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
                msg_before = fork_message(message, {"text": text_before})
                # No x_agent_switch - goes to current agent
                output_messages.append(msg_before)

            # Message 2: empty text with switch flag - triggers switch, nothing sent
            switch_msg = fork_message(message, {
                "text": "",
                "x_agent_switch": {
                    "target": match.agent_id,
                    "confidence": round(match.score, 3),
                    "source": "dictare/agent-filter",
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
            if agent_id in AgentManager.RESERVED_AGENT_IDS:
                continue
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

        When user says "agent dictare", we remove "agent dictare" and
        anything after it. This handles cases where Whisper splits
        the agent name (e.g., "dictare" -> "Fox type").

        Args:
            text: Original text.
            match: The agent match found.
            tokens: Normalized tokens.

        Returns:
            Text with trigger pattern and everything after removed.
        """
        # Find trigger word and remove everything from it to the end
        # This handles multi-word transcriptions like "Fox type" for "dictare"
        pattern = rf"\b{match.trigger_word}\b.*$"
        cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE).rstrip()

        return cleaned
