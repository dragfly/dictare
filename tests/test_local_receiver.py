"""Tests for LocalReceiver - OpenVIP message consumption and keyboard injection."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class MockConfig:
    """Mock config for testing."""

    def __init__(self) -> None:
        self.output = MagicMock()
        self.output.typing_delay_ms = 0
        self.output.submit_keys = "enter"
        self.output.newline_keys = "shift+enter"


class MockInjector:
    """Mock keyboard injector for testing."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.available = True
        self.raise_on_type = False

    def is_available(self) -> bool:
        return self.available

    def type_text(
        self,
        text: str,
        delay_ms: int = 0,
        auto_enter: bool = False,
        submit_keys: str = "enter",
        newline_keys: str = "shift+enter",
    ) -> None:
        if self.raise_on_type:
            raise RuntimeError("Simulated injector error")
        self.calls.append({
            "text": text,
            "delay_ms": delay_ms,
            "auto_enter": auto_enter,
            "submit_keys": submit_keys,
            "newline_keys": newline_keys,
        })


class TestLocalReceiverInit:
    """Test LocalReceiver initialization."""

    def test_initial_state(self) -> None:
        """Receiver starts in stopped state."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        assert receiver._running is False
        assert receiver._worker is None
        assert receiver._injector is None
        assert receiver._queue is not None

    def test_has_injector_lock(self) -> None:
        """Receiver has lock for thread-safe injector access."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        assert hasattr(receiver, "_injector_lock")
        assert isinstance(receiver._injector_lock, type(threading.Lock()))


class TestLocalReceiverLifecycle:
    """Test start/stop lifecycle."""

    def test_start_creates_worker_thread(self) -> None:
        """Start creates and starts worker thread."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        # Mock the injector creation
        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            assert receiver._running is True
            assert receiver._worker is not None
            assert receiver._worker.is_alive()
            assert receiver._injector is mock_injector

            receiver.stop()

    def test_start_is_idempotent(self) -> None:
        """Starting twice doesn't create multiple workers."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()
            first_worker = receiver._worker

            receiver.start()  # Second start
            assert receiver._worker is first_worker

            receiver.stop()

    def test_stop_terminates_worker(self) -> None:
        """Stop terminates worker thread."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()
            worker = receiver._worker

            receiver.stop()

            assert receiver._running is False
            assert receiver._worker is None
            assert not worker.is_alive()

    def test_stop_clears_injector(self) -> None:
        """Stop clears the injector reference."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()
            assert receiver._injector is not None

            receiver.stop()
            assert receiver._injector is None

    def test_stop_is_idempotent(self) -> None:
        """Stopping twice doesn't crash."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()
            receiver.stop()
            receiver.stop()  # Second stop should not crash


class TestLocalReceiverSend:
    """Test message sending."""

    def test_send_queues_message(self) -> None:
        """Send queues the message."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            message = {"openvip": "1.0", "type": "message", "text": "hello"}
            result = receiver.send(message)

            assert result is True
            receiver.stop()

    def test_send_returns_false_when_stopped(self) -> None:
        """Send returns False when receiver is stopped."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        message = {"openvip": "1.0", "type": "message", "text": "hello"}
        result = receiver.send(message)

        assert result is False


class TestLocalReceiverMessageProcessing:
    """Test message processing."""

    def test_processes_message_type_message(self) -> None:
        """Processes messages with type 'message'."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            message = {"openvip": "1.0", "type": "message", "text": "hello world"}
            receiver.send(message)

            # Wait for processing
            time.sleep(0.2)

            assert len(mock_injector.calls) == 1
            assert mock_injector.calls[0]["text"] == "hello world"
            assert mock_injector.calls[0]["auto_enter"] is False

            receiver.stop()

    def test_ignores_non_message_types(self) -> None:
        """Ignores messages with type other than 'message'."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            # Send non-message types
            receiver.send({"openvip": "1.0", "type": "partial", "text": "hello"})
            receiver.send({"openvip": "1.0", "type": "state", "state": "listening"})
            receiver.send({"openvip": "1.0", "type": "start"})

            time.sleep(0.2)

            assert len(mock_injector.calls) == 0

            receiver.stop()

    def test_x_submit_sets_auto_enter(self) -> None:
        """x_submit flag sets auto_enter=True."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            message = {"openvip": "1.0", "type": "message", "text": "hello", "x_submit": {"enter": True}}
            receiver.send(message)

            time.sleep(0.2)

            assert len(mock_injector.calls) == 1
            assert mock_injector.calls[0]["auto_enter"] is True

            receiver.stop()

    def test_x_visual_newline_disables_auto_enter(self) -> None:
        """x_visual_newline flag disables auto_enter even with x_submit."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            # Both flags set - visual_newline takes precedence
            message = {
                "openvip": "1.0",
                "type": "message",
                "text": "hello",
                "x_submit": {"enter": True},
                "x_visual_newline": True,
            }
            receiver.send(message)

            time.sleep(0.2)

            assert len(mock_injector.calls) == 1
            assert mock_injector.calls[0]["auto_enter"] is False

            receiver.stop()

    def test_uses_config_typing_delay(self) -> None:
        """Uses typing delay from config."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        config.output.typing_delay_ms = 50
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            message = {"openvip": "1.0", "type": "message", "text": "hello"}
            receiver.send(message)

            time.sleep(0.2)

            assert mock_injector.calls[0]["delay_ms"] == 50

            receiver.stop()


class TestLocalReceiverErrorHandling:
    """Test error handling in worker thread."""

    def test_worker_survives_process_message_exception(self) -> None:
        """Worker thread survives exceptions from _process_message."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        mock_injector.raise_on_type = True  # Will raise on first message

        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            # Send message that will cause exception
            message1 = {"openvip": "1.0", "type": "message", "text": "fail"}
            receiver.send(message1)

            time.sleep(0.2)

            # Worker should still be alive
            assert receiver._worker.is_alive()

            # Fix the injector
            mock_injector.raise_on_type = False

            # Send another message
            message2 = {"openvip": "1.0", "type": "message", "text": "success"}
            receiver.send(message2)

            time.sleep(0.2)

            # Should have processed the second message
            assert len(mock_injector.calls) == 1
            assert mock_injector.calls[0]["text"] == "success"

            receiver.stop()

    def test_exception_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Exceptions are logged with message ID."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        mock_injector.raise_on_type = True

        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            with caplog.at_level(logging.ERROR):
                receiver.start()

                message = {
                    "openvip": "1.0",
                    "type": "message",
                    "id": "test-msg-123",
                    "text": "fail",
                }
                receiver.send(message)

                time.sleep(0.2)

                receiver.stop()

            # Check error was logged
            assert any("test-msg-123" in record.message for record in caplog.records)
            assert any("Simulated injector error" in record.message for record in caplog.records)


class TestLocalReceiverThreadSafety:
    """Test thread safety of LocalReceiver."""

    def test_concurrent_sends_are_safe(self) -> None:
        """Multiple threads can send messages concurrently."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            errors = []
            message_count = 50

            def send_messages() -> None:
                try:
                    for i in range(message_count):
                        receiver.send({
                            "openvip": "1.0",
                            "type": "message",
                            "text": f"msg-{threading.current_thread().name}-{i}",
                        })
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=send_messages) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Wait for all messages to be processed
            time.sleep(0.5)

            assert len(errors) == 0
            # All messages should be processed (5 threads * 50 messages)
            assert len(mock_injector.calls) == 5 * message_count

            receiver.stop()

    def test_stop_during_processing_is_safe(self) -> None:
        """Stopping while processing messages doesn't crash."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            # Queue many messages
            for i in range(100):
                receiver.send({
                    "openvip": "1.0",
                    "type": "message",
                    "text": f"msg-{i}",
                })

            # Stop immediately - should not crash
            receiver.stop()

            assert receiver._running is False

    def test_injector_lock_prevents_race(self) -> None:
        """Injector lock prevents race between stop and process."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        mock_injector = MockInjector()
        errors = []

        with patch.object(receiver, "_create_injector", return_value=mock_injector):
            receiver.start()

            def send_many() -> None:
                try:
                    for _ in range(100):
                        receiver.send({
                            "openvip": "1.0",
                            "type": "message",
                            "text": "test",
                        })
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

            def stop_after_delay() -> None:
                try:
                    time.sleep(0.05)
                    receiver.stop()
                except Exception as e:
                    errors.append(e)

            t1 = threading.Thread(target=send_many)
            t2 = threading.Thread(target=stop_after_delay)

            t1.start()
            t2.start()
            t1.join()
            t2.join()

            # No exceptions should occur
            assert len(errors) == 0


class TestLocalReceiverQueue:
    """Test queue access."""

    def test_queue_property_returns_queue(self) -> None:
        """queue property returns the internal queue."""
        from voxtype.output.local import LocalReceiver

        config = MockConfig()
        receiver = LocalReceiver(config)

        q = receiver.queue
        assert isinstance(q, queue.Queue)
        assert q is receiver._queue
