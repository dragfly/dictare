"""Audio feedback policy — decides whether sounds should play.

Encapsulates focus state and per-event gating logic.
Thread-safe via lock (microsecond-level dict ops, no contention).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dictare.config import AudioConfig

_UNFOCUS_DEBOUNCE_S: float = 0.5  # delay before applying focus-out (catches flicker)

class AudioFeedbackPolicy:
    """Decides whether audio feedback should play for a given event.

    Focus-gated events are silenced when the target agent's terminal
    is focused (the user can already see what's happening).
    Non-gated events always play regardless of focus.

    Focus-out events are debounced (500ms) to handle terminal focus
    flicker — some terminals send focus-in/out rapidly during text
    injection or window transitions.  Focus-in is applied immediately.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._focus: dict[str, bool] = {}  # agent_id → focused
        self._timers: dict[str, threading.Timer] = {}  # pending unfocus timers

    def set_focus(self, agent_id: str, focused: bool) -> None:
        """Update focus state for an agent's terminal.

        Focus-in is applied immediately (suppress sounds right away).
        Focus-out is debounced to catch rapid focus flicker.
        """
        if focused:
            with self._lock:
                self._focus[agent_id] = True
                timer = self._timers.pop(agent_id, None)
            if timer:
                timer.cancel()
        else:
            with self._lock:
                timer = self._timers.get(agent_id)
            if timer:
                timer.cancel()

            def _apply_unfocus() -> None:
                with self._lock:
                    self._focus[agent_id] = False
                    self._timers.pop(agent_id, None)

            t = threading.Timer(_UNFOCUS_DEBOUNCE_S, _apply_unfocus)
            t.daemon = True
            t.start()
            with self._lock:
                self._timers[agent_id] = t

    def remove_agent(self, agent_id: str) -> None:
        """Clean up focus state when an agent disconnects."""
        with self._lock:
            self._focus.pop(agent_id, None)
            timer = self._timers.pop(agent_id, None)
        if timer:
            timer.cancel()

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
            logger.debug("should_play(%s): no current agent → play", event)
            return True

        with self._lock:
            focused = self._focus.get(current_agent_id)
            all_focus = dict(self._focus)

        # No focus info → default to play (terminal may not support reporting)
        if focused is None:
            logger.info("should_play(%s): agent=%s has no focus info (known: %s) → play", event, current_agent_id, all_focus)
            return True

        play = not focused
        logger.info("should_play(%s): agent=%s focused=%s → %s", event, current_agent_id, focused, "play" if play else "SKIP")
        return play
