"""Tests for input/manager.py — InputManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dictare.input.base import InputEvent, InputSource
from dictare.input.manager import InputManager


class MockSource(InputSource):
    def __init__(self, name: str = "mock") -> None:
        self._name = name
        self._running = False
        self._callback = None

    def start(self, on_input) -> bool:
        self._callback = on_input
        self._running = True
        return True

    def stop(self) -> None:
        self._running = False

    @property
    def source_name(self) -> str:
        return self._name

    @property
    def is_running(self) -> bool:
        return self._running


class TestInputManagerBasics:
    def test_source_count_initially_zero(self) -> None:
        executor = MagicMock()
        mgr = InputManager(executor)
        assert mgr.source_count == 0

    def test_running_sources_empty(self) -> None:
        executor = MagicMock()
        mgr = InputManager(executor)
        assert mgr.running_sources == []


class TestInputManagerLoadKeyboardShortcuts:
    def test_loads_valid_shortcuts(self) -> None:
        executor = MagicMock()
        mgr = InputManager(executor)
        shortcuts = [
            {"keys": "Ctrl+L", "command": "toggle-listening"},
            {"keys": "Ctrl+Shift+N", "command": "project-next"},
        ]
        mgr.load_keyboard_shortcuts(shortcuts)
        assert mgr.source_count == 1

    def test_skips_empty_keys(self) -> None:
        executor = MagicMock()
        mgr = InputManager(executor)
        shortcuts = [
            {"keys": "", "command": "toggle-listening"},
            {"keys": "Ctrl+L", "command": ""},
        ]
        mgr.load_keyboard_shortcuts(shortcuts)
        assert mgr.source_count == 0

    def test_no_source_when_no_bindings(self) -> None:
        executor = MagicMock()
        mgr = InputManager(executor)
        mgr.load_keyboard_shortcuts([])
        assert mgr.source_count == 0


class TestInputManagerStartStop:
    def test_start_starts_all_sources(self) -> None:
        executor = MagicMock()
        mgr = InputManager(executor)
        src1 = MockSource("src1")
        src2 = MockSource("src2")
        mgr._sources = [src1, src2]

        mgr.start()
        assert src1.is_running
        assert src2.is_running

    def test_stop_stops_all_sources(self) -> None:
        executor = MagicMock()
        mgr = InputManager(executor)
        src1 = MockSource("src1")
        src2 = MockSource("src2")
        mgr._sources = [src1, src2]

        mgr.start()
        mgr.stop()
        assert not src1.is_running
        assert not src2.is_running

    def test_running_sources_returns_names(self) -> None:
        executor = MagicMock()
        mgr = InputManager(executor)
        src1 = MockSource("keyboard")
        src2 = MockSource("device")
        mgr._sources = [src1, src2]

        mgr.start()
        assert set(mgr.running_sources) == {"keyboard", "device"}


class TestInputManagerHandleInput:
    def test_routes_to_app_command(self) -> None:
        executor = MagicMock()
        executor.execute.return_value = True
        mgr = InputManager(executor)

        event = InputEvent(command="toggle-listening", source="keyboard")
        mgr._handle_input(event)
        executor.execute.assert_called_once_with("toggle-listening", {})

    def test_routes_to_target_when_not_app_command(self) -> None:
        executor = MagicMock()
        executor.execute.return_value = False
        mgr = InputManager(executor)

        target_events = []
        mgr.set_target_command_handler(lambda e: target_events.append(e))

        event = InputEvent(command="custom-cmd", source="keyboard")
        mgr._handle_input(event)
        assert len(target_events) == 1
        assert target_events[0].command == "custom-cmd"

    def test_no_error_when_no_target_handler(self) -> None:
        executor = MagicMock()
        executor.execute.return_value = False
        mgr = InputManager(executor)

        event = InputEvent(command="unknown", source="keyboard")
        mgr._handle_input(event)  # Should not raise


class TestInputManagerLoadDeviceProfiles:
    def test_no_error_when_dir_missing(self, tmp_path) -> None:
        executor = MagicMock()
        mgr = InputManager(executor)
        mgr.load_device_profiles(tmp_path / "nonexistent")
        assert mgr.source_count == 0

    def test_no_profiles_in_empty_dir(self, tmp_path) -> None:
        executor = MagicMock()
        mgr = InputManager(executor)
        mgr.load_device_profiles(tmp_path)
        assert mgr.source_count == 0
