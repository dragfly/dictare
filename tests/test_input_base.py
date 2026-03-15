"""Tests for input/base.py — InputEvent, InputSource."""

from __future__ import annotations

from dictare.input.base import InputEvent, InputSource


class TestInputEvent:
    def test_defaults(self) -> None:
        event = InputEvent(command="test")
        assert event.command == "test"
        assert event.args == {}
        assert event.source == "unknown"

    def test_custom_values(self) -> None:
        event = InputEvent(command="switch", args={"index": 1}, source="keyboard")
        assert event.command == "switch"
        assert event.args == {"index": 1}
        assert event.source == "keyboard"

    def test_args_not_shared(self) -> None:
        """Each event gets its own args dict."""
        e1 = InputEvent(command="a")
        e2 = InputEvent(command="b")
        e1.args["x"] = 1
        assert "x" not in e2.args


class ConcreteInputSource(InputSource):
    """Concrete implementation for testing the abstract base."""

    def __init__(self) -> None:
        self._started = False

    def start(self, on_input) -> bool:
        self._started = True
        return True

    def stop(self) -> None:
        self._started = False

    @property
    def source_name(self) -> str:
        return "test-source"


class TestInputSource:
    def test_is_running_default_false(self) -> None:
        src = ConcreteInputSource()
        assert src.is_running is False

    def test_source_name(self) -> None:
        src = ConcreteInputSource()
        assert src.source_name == "test-source"

    def test_start_and_stop(self) -> None:
        src = ConcreteInputSource()
        result = src.start(lambda e: None)
        assert result is True
        assert src._started is True
        src.stop()
        assert src._started is False
