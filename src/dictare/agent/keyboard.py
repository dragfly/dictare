"""Keyboard agent - simulates keystrokes locally.

This agent receives OpenVIP messages and injects them via keyboard
simulation (Quartz on macOS, ydotool on Linux).
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dictare.agent.base import BaseAgent, OpenVIPMessage

if TYPE_CHECKING:
    from dictare.config import Config

logger = logging.getLogger(__name__)


@dataclass
class _QueuedInjection:
    """Queued keyboard injection with completion signaling."""

    message: OpenVIPMessage
    done: threading.Event
    result: list[bool]


class KeyboardAgent(BaseAgent):
    """Agent that injects text via keyboard simulation.

    Uses a background worker thread to process messages asynchronously,
    preventing blocking the main thread during keystroke injection.

    Thread-safety:
    - Messages are queued and processed by a single worker thread
    - Injector access is protected by a lock
    """

    # Special agent ID for keyboard
    KEYBOARD_ID = "__keyboard__"

    def __init__(self, config: Config) -> None:
        """Initialize keyboard agent.

        Args:
            config: Application configuration for auto_enter, typing_delay, etc.
        """
        super().__init__(self.KEYBOARD_ID)
        self.config = config
        self._queue: queue.Queue[_QueuedInjection | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._injector: Any = None
        self._injector_lock = threading.Lock()

    def _create_injector(self) -> Any:
        """Create keyboard injector for current platform."""
        if sys.platform == "darwin":
            from dictare.agent.injection.quartz import QuartzInjector

            injector = QuartzInjector()
            if not injector.is_available():
                raise RuntimeError(
                    "Quartz text injection not available. "
                    "Grant Accessibility permission in System Preferences > "
                    "Security & Privacy > Privacy > Accessibility"
                )
            return injector
        else:
            from dictare.agent.injection.ydotool import YdotoolInjector

            injector = YdotoolInjector()
            if not injector.is_available():
                raise RuntimeError(
                    "ydotool not available. Ensure ydotoold is running:\n"
                    "  sudo ydotoold &\n"
                    "Or install ydotool: apt install ydotool / pacman -S ydotool"
                )
            return injector

    def start(self) -> None:
        """Start the keyboard agent worker thread."""
        if self._running:
            return

        with self._injector_lock:
            self._injector = self._create_injector()
        self._running = True
        self._worker = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="keyboard-agent",
        )
        self._worker.start()

    def stop(self) -> None:
        """Stop the keyboard agent."""
        if not self._running:
            return

        self._running = False
        # Send sentinel to unblock worker
        self._queue.put(None)

        if self._worker:
            self._worker.join(timeout=2.0)
            self._worker = None

        with self._injector_lock:
            self._injector = None

    def send(self, message: OpenVIPMessage) -> bool:
        """Queue a message for keyboard injection.

        Args:
            message: OpenVIP message to inject.

        Returns:
            True if queued successfully.
        """
        if not self._running:
            logger.warning("KeyboardAgent not running, message dropped")
            return False

        done = threading.Event()
        result: list[bool] = [False]
        self._queue.put(_QueuedInjection(message=message, done=done, result=result))
        timeout_s = self._estimate_timeout_seconds(message)
        if not done.wait(timeout=timeout_s):
            logger.warning("Keyboard injection timed out after %.1fs", timeout_s)
            return False
        return result[0]

    def _worker_loop(self) -> None:
        """Background worker that processes queued messages."""
        while self._running:
            try:
                item = self._queue.get(timeout=0.5)
                if item is None:
                    # Sentinel - stop requested
                    break
                ok = self._process_message(item.message)
                item.result[0] = ok
                item.done.set()
            except queue.Empty:
                continue
            except Exception as e:
                logger.exception(f"KeyboardAgent worker error: {e}")

    def _process_message(self, message: OpenVIPMessage) -> bool:
        """Process a single OpenVIP message.

        Args:
            message: OpenVIP message dict.
        """
        text = message.get("text", "")
        x_input = message.get("x_input", {})
        submit = x_input.get("submit", False) if isinstance(x_input, dict) else False
        visual_newline = message.get("visual_newline", False)

        # Get config values
        delay_ms = self.config.output.typing_delay_ms
        auto_enter = self.config.output.auto_enter if not submit else True
        submit_keys = self.config.output.submit_keys
        newline_keys = self.config.output.newline_keys

        with self._injector_lock:
            if not self._injector:
                logger.warning("Keyboard injector not available")
                return False

            # Handle visual newline (no submit)
            if visual_newline and not text:
                return bool(self._injector.send_newline())

            # Handle submit-only (no text)
            if submit and not text:
                return bool(self._injector.send_submit())

            # Normal text injection
            return bool(self._injector.type_text(
                text,
                delay_ms=delay_ms,
                auto_enter=auto_enter,
                submit_keys=submit_keys,
                newline_keys=newline_keys,
            ))

    def _estimate_timeout_seconds(self, message: OpenVIPMessage) -> float:
        """Estimate a reasonable timeout for synchronous send()."""
        text = str(message.get("text", ""))
        delay_ms = max(0, int(self.config.output.typing_delay_ms))
        # Base timeout + per-character delay budget + small safety margin.
        return max(2.0, 1.0 + (len(text) * delay_ms / 1000.0) + 1.0)
