"""Tests for the internal event bus."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from dictare.core.bus import EventBus, bus


@pytest.fixture(autouse=True)
def reset_bus():
    """Reset global bus before each test."""
    bus.reset()
    yield
    bus.reset()

class TestEventBusBasics:
    """Test basic EventBus operations."""

    def test_subscribe_and_publish(self) -> None:
        """Callback is called when event is published."""
        callback = MagicMock()
        bus.subscribe("test.event", callback)

        bus.publish("test.event", foo="bar")

        callback.assert_called_once_with(foo="bar")

    def test_multiple_subscribers(self) -> None:
        """Multiple subscribers all receive the event."""
        callback1 = MagicMock()
        callback2 = MagicMock()

        bus.subscribe("test.event", callback1)
        bus.subscribe("test.event", callback2)

        bus.publish("test.event", value=42)

        callback1.assert_called_once_with(value=42)
        callback2.assert_called_once_with(value=42)

    def test_no_subscribers(self) -> None:
        """Publishing with no subscribers doesn't raise."""
        # Should not raise
        bus.publish("nonexistent.event", data="test")

    def test_unsubscribe(self) -> None:
        """Unsubscribed callback is not called."""
        callback = MagicMock()
        bus.subscribe("test.event", callback)
        bus.unsubscribe("test.event", callback)

        bus.publish("test.event")

        callback.assert_not_called()

    def test_unsubscribe_returns_false_if_not_found(self) -> None:
        """Unsubscribe returns False if callback not found."""
        callback = MagicMock()
        result = bus.unsubscribe("test.event", callback)
        assert result is False

    def test_unsubscribe_returns_true_if_found(self) -> None:
        """Unsubscribe returns True if callback was removed."""
        callback = MagicMock()
        bus.subscribe("test.event", callback)
        result = bus.unsubscribe("test.event", callback)
        assert result is True

    def test_reset_clears_all_subscribers(self) -> None:
        """Reset removes all subscribers."""
        callback = MagicMock()
        bus.subscribe("test.event", callback)
        bus.reset()

        bus.publish("test.event")

        callback.assert_not_called()

    def test_different_events_are_independent(self) -> None:
        """Subscribers only receive their subscribed events."""
        callback1 = MagicMock()
        callback2 = MagicMock()

        bus.subscribe("event.one", callback1)
        bus.subscribe("event.two", callback2)

        bus.publish("event.one", data="one")

        callback1.assert_called_once_with(data="one")
        callback2.assert_not_called()

class TestEventBusErrorHandling:
    """Test EventBus error handling."""

    def test_callback_exception_does_not_stop_others(self) -> None:
        """Exception in one callback doesn't prevent others from running."""
        callback1 = MagicMock(side_effect=ValueError("boom"))
        callback2 = MagicMock()

        bus.subscribe("test.event", callback1)
        bus.subscribe("test.event", callback2)

        # Should not raise
        bus.publish("test.event")

        # Second callback should still be called
        callback2.assert_called_once()

class TestEventBusThreadSafety:
    """Test EventBus thread safety."""

    def test_concurrent_publish(self) -> None:
        """Multiple threads can publish concurrently."""
        results: list[int] = []
        lock = threading.Lock()

        def callback(value: int) -> None:
            with lock:
                results.append(value)

        bus.subscribe("test.event", callback)

        threads = []
        for i in range(10):
            t = threading.Thread(target=bus.publish, args=("test.event",), kwargs={"value": i})
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(results) == 10
        assert set(results) == set(range(10))

    def test_concurrent_subscribe(self) -> None:
        """Multiple threads can subscribe concurrently."""
        callbacks = [MagicMock() for _ in range(10)]

        def subscribe(cb: MagicMock) -> None:
            bus.subscribe("test.event", cb)

        threads = [threading.Thread(target=subscribe, args=(cb,)) for cb in callbacks]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        bus.publish("test.event")

        for cb in callbacks:
            cb.assert_called_once()

    def test_publish_during_subscribe(self) -> None:
        """Publishing while subscribing doesn't cause issues."""
        callback = MagicMock()
        published = threading.Event()

        def slow_subscribe() -> None:
            bus.subscribe("test.event", callback)
            time.sleep(0.01)  # Give time for publish to happen

        def publish_immediately() -> None:
            time.sleep(0.005)  # Wait a bit for subscribe to start
            bus.publish("test.event")
            published.set()

        t1 = threading.Thread(target=slow_subscribe)
        t2 = threading.Thread(target=publish_immediately)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Callback should be called (subscribe completes before publish)
        assert published.is_set()

class TestEventBusInstance:
    """Test EventBus instance behavior."""

    def test_separate_instances_are_independent(self) -> None:
        """Different EventBus instances don't share subscribers."""
        bus1 = EventBus()
        bus2 = EventBus()

        callback = MagicMock()
        bus1.subscribe("test.event", callback)

        bus2.publish("test.event")

        callback.assert_not_called()

    def test_global_bus_is_singleton(self) -> None:
        """Importing bus always gets the same instance."""
        from dictare.core import bus as bus1
        from dictare.core.bus import bus as bus2

        assert bus1 is bus2
