"""Local receiver - consumes OpenVIP messages and injects via keyboard."""

from __future__ import annotations

import queue
import sys
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from voxtype.config import Config

# OpenVIP message type
OpenVIPMessage = dict[str, Any]

class LocalReceiver:
    """Receives OpenVIP messages from in-memory queue and injects via keyboard.

    This provides the same architecture as socket-based agents but for local mode:
    - Engine produces OpenVIP messages
    - LocalReceiver consumes them and injects via keyboard

    This allows a uniform message-based architecture regardless of transport.
    """

    def __init__(self, config: Config) -> None:
        """Initialize local receiver.

        Args:
            config: Application configuration for auto_enter, typing_delay, etc.
        """
        self.config = config
        self._queue: queue.Queue[OpenVIPMessage | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._injector: Any = None

    def _create_injector(self) -> Any:
        """Create keyboard injector for current platform."""
        if sys.platform == "darwin":
            from voxtype.injection.quartz import QuartzInjector

            injector = QuartzInjector()
            if not injector.is_available():
                raise RuntimeError(
                    "Quartz text injection not available. "
                    "Grant Accessibility permission in System Preferences > "
                    "Security & Privacy > Privacy > Accessibility"
                )
            return injector
        else:
            from voxtype.injection.ydotool import YdotoolInjector

            injector = YdotoolInjector()
            if not injector.is_available():
                raise RuntimeError(
                    "ydotool not available. Ensure ydotoold is running:\n"
                    "  sudo ydotoold &\n"
                    "Or install ydotool: apt install ydotool / pacman -S ydotool"
                )
            return injector

    def start(self) -> None:
        """Start the receiver worker thread."""
        if self._running:
            return

        self._injector = self._create_injector()
        self._running = True
        self._worker = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="local-receiver",
        )
        self._worker.start()

    def stop(self) -> None:
        """Stop the receiver worker thread."""
        if not self._running:
            return

        self._running = False
        # Send None to unblock the queue
        self._queue.put(None)

        if self._worker:
            self._worker.join(timeout=1.0)
            self._worker = None

    def send(self, message: OpenVIPMessage) -> bool:
        """Send an OpenVIP message to be injected.

        Args:
            message: OpenVIP message with 'text', 'x_submit', 'x_visual_newline', etc.

        Returns:
            True if queued successfully.
        """
        if not self._running:
            return False
        self._queue.put(message)
        return True

    def _worker_loop(self) -> None:
        """Worker thread that consumes messages and injects."""
        while self._running:
            try:
                message = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if message is None:
                break

            self._process_message(message)

    def _process_message(self, message: OpenVIPMessage) -> None:
        """Process a single OpenVIP message.

        Args:
            message: OpenVIP message to process.
        """
        if not self._injector:
            return

        msg_type = message.get("type", "message")
        if msg_type != "message":
            return

        text = message.get("text", "")
        x_submit = message.get("x_submit", False)
        x_visual_newline = message.get("x_visual_newline", False)

        # Determine auto_enter based on message flags
        # x_submit=true means auto_enter=true (send Enter)
        # x_visual_newline=true means auto_enter=false (send Shift+Enter)
        auto_enter = x_submit and not x_visual_newline

        self._injector.type_text(
            text,
            delay_ms=self.config.output.typing_delay_ms,
            auto_enter=auto_enter,
        )

    @property
    def queue(self) -> queue.Queue[OpenVIPMessage | None]:
        """Get the message queue for direct access."""
        return self._queue
