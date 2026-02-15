"""Internal event bus for decoupled component communication.

Design Decision: Custom Implementation vs Library (e.g., Blinker)
-----------------------------------------------------------------
We intentionally implement a custom EventBus rather than using an external
library like Blinker or PyPubSub. This is NOT our default approach - we
generally prefer well-maintained, community-standard libraries.

However, in this specific case:
1. The implementation is ~40 lines of code (trivially simple)
2. Zero additional dependencies
3. Full control over logging integration
4. Thread-safe by design for our use case

If requirements grow significantly, we should evaluate migrating to Blinker.

Usage
-----
    from voxtype.core import bus

    # Subscribe to events
    bus.subscribe("agents.changed", lambda agent_ids: print(agent_ids))

    # Publish events
    bus.publish("agents.changed", agent_ids=["voxtype", "koder"])

Thread Safety
-------------
The bus is thread-safe. Multiple threads can publish and subscribe
concurrently. Callbacks are executed synchronously in the publisher's thread.

Testing
-------
Use `bus.reset()` in test fixtures to clear all subscribers:

    @pytest.fixture(autouse=True)
    def reset_event_bus():
        bus.reset()
        yield

Events
------
See docs/events.md for the list of events published by voxtype components.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

class EventBus:
    """Thread-safe internal event bus for publish/subscribe communication.

    This is a singleton - use the global `bus` instance from this module.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[..., Any]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event: str, callback: Callable[..., Any]) -> None:
        """Subscribe to an event.

        Args:
            event: Event name (e.g., "agents.changed").
            callback: Function to call when event is published.
                      Receives keyword arguments from publish().
        """
        with self._lock:
            if event not in self._subscribers:
                self._subscribers[event] = []
            self._subscribers[event].append(callback)
            logger.debug("event_subscribe", extra={"event": event})

    def unsubscribe(self, event: str, callback: Callable[..., Any]) -> bool:
        """Unsubscribe from an event.

        Args:
            event: Event name.
            callback: The callback to remove.

        Returns:
            True if callback was removed, False if not found.
        """
        with self._lock:
            if event in self._subscribers:
                try:
                    self._subscribers[event].remove(callback)
                    logger.debug("event_unsubscribe", extra={"event": event})
                    return True
                except ValueError:
                    pass
        return False

    def publish(self, event: str, **data: Any) -> None:
        """Publish an event to all subscribers.

        Callbacks are executed synchronously in the caller's thread.
        Exceptions in callbacks are logged but do not stop other callbacks.

        Args:
            event: Event name (e.g., "agents.changed").
            **data: Keyword arguments passed to all callbacks.
        """
        # Copy subscribers list to avoid holding lock during callbacks
        with self._lock:
            callbacks = self._subscribers.get(event, [])[:]

        if not callbacks:
            return

        logger.debug("event_publish", extra={"event": event, **data})

        for callback in callbacks:
            try:
                callback(**data)
            except Exception:
                callback_name = getattr(callback, "__name__", repr(callback))
                logger.exception(
                    "event_callback_error",
                    extra={"event": event, "callback": callback_name},
                )

    def reset(self) -> None:
        """Clear all subscribers. Use in tests only."""
        with self._lock:
            self._subscribers.clear()
            logger.debug("event_bus_reset")

# Global singleton instance
bus = EventBus()
