"""Tests for plugins/base.py — Plugin protocol and BasePlugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dictare.plugins.base import BasePlugin, Plugin


class ConcretePlugin(BasePlugin):
    @property
    def name(self) -> str:
        return "test-plugin"

    @property
    def description(self) -> str:
        return "A test plugin"

    def get_commands(self):
        return None


class TestPluginProtocol:
    def test_concrete_plugin_is_plugin(self) -> None:
        plugin = ConcretePlugin()
        assert isinstance(plugin, Plugin)


class TestBasePlugin:
    def test_name(self) -> None:
        plugin = ConcretePlugin()
        assert plugin.name == "test-plugin"

    def test_description(self) -> None:
        plugin = ConcretePlugin()
        assert plugin.description == "A test plugin"

    def test_get_commands_default(self) -> None:
        plugin = ConcretePlugin()
        assert plugin.get_commands() is None

    def test_services_raises_before_load(self) -> None:
        plugin = ConcretePlugin()
        with pytest.raises(RuntimeError, match="not loaded"):
            _ = plugin.services

    def test_on_load_stores_services(self) -> None:
        plugin = ConcretePlugin()
        registry = MagicMock()
        plugin.on_load(registry)
        assert plugin.services is registry

    def test_services_accessible_after_load(self) -> None:
        plugin = ConcretePlugin()
        registry = MagicMock()
        plugin.on_load(registry)
        # Should not raise
        svc = plugin.services
        assert svc is registry
