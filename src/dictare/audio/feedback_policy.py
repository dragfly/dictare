"""Audio feedback policy — decides whether sounds should play.

Encapsulates focus state and per-event gating logic.
Thread-safe via lock (microsecond-level dict ops, no contention).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictare.config import AudioConfig


class AudioFeedbackPolicy:
    """Decides whether audio feedback should play for a given event.

    Focus-gated events are silenced when the target agent's terminal
    is focused (the user can already see what's happening).
    Non-gated events always play regardless of focus.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._focus: dict[str, bool] = {}  # agent_id → focused

    def set_focus(self, agent_id: str, focused: bool) -> None:
        """Update focus state for an agent's terminal."""
        with self._lock:
            self._focus[agent_id] = focused

    def remove_agent(self, agent_id: str) -> None:
        """Clean up focus state when an agent disconnects."""
        with self._lock:
            self._focus.pop(agent_id, None)

    def should_play(
        self,
        event: str,
        current_agent_id: str | None,
        audio_config: AudioConfig,
    ) -> bool:
        """Return True if the sound for *event* should play.

        Non-focus-gated events always return True.
        Focus-gated events return False only when the current agent's
        terminal is known to be focused.  No focus info → True (safe default).
        """
        # Check per-event focus_gated flag from config
        sound_cfg = audio_config.sounds.get(event)
        if sound_cfg is None or not sound_cfg.focus_gated:
            return True

        if current_agent_id is None:
            return True

        with self._lock:
            focused = self._focus.get(current_agent_id)

        # No focus info → default to play (terminal may not support reporting)
        if focused is None:
            return True

        return not focused
