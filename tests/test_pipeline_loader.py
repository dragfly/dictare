"""Tests for the pipeline plugin loader (DI-based step construction)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from voxtype.pipeline.base import Pipeline, PipelineResult
from voxtype.pipeline.loader import (
    _BUILTIN_STEPS,
    PipelineLoader,
    get_step_registry,
    register_step,
)

# ---------------------------------------------------------------------------
# Fixtures: lightweight step stubs
# ---------------------------------------------------------------------------


@dataclass
class _StubFilter:
    """Filter with config-only params."""

    triggers: list[str] = field(default_factory=lambda: ["default"])
    confidence: float = 0.9

    @property
    def name(self) -> str:
        return "stub_filter"

    def process(self, message: dict) -> PipelineResult:
        return PipelineResult.passed(message)


@dataclass
class _StubExecutor:
    """Executor with service-only param."""

    switch_fn: object = None

    @property
    def name(self) -> str:
        return "stub_executor"

    @property
    def field(self) -> str:
        return "x_stub"

    def process(self, message: dict) -> PipelineResult:
        return PipelineResult.passed(message)


@dataclass
class _MixedStep:
    """Step requiring both config and service params."""

    agent_ids: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=lambda: ["agent"])
    match_threshold: float = 0.5
    subscribe_to_events: bool = False

    @property
    def name(self) -> str:
        return "mixed_step"

    def process(self, message: dict) -> PipelineResult:
        return PipelineResult.passed(message)


@pytest.fixture()
def _isolated_registry(monkeypatch):
    """Ensure tests don't pollute the global registry."""
    original = _BUILTIN_STEPS.copy()
    yield
    _BUILTIN_STEPS.clear()
    _BUILTIN_STEPS.update(original)


# ---------------------------------------------------------------------------
# 1. Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_register_and_get(self, _isolated_registry):
        register_step("my_filter", _StubFilter)
        reg = get_step_registry()
        assert "my_filter" in reg
        assert reg["my_filter"] is _StubFilter

    def test_get_returns_copy(self, _isolated_registry):
        reg = get_step_registry()
        reg["garbage"] = int
        assert "garbage" not in get_step_registry()


# ---------------------------------------------------------------------------
# 2-5. _build_step DI
# ---------------------------------------------------------------------------


class TestBuildStep:
    def test_config_only(self, _isolated_registry):
        """InputFilter-like: all params from config."""
        register_step("stub_filter", _StubFilter)
        loader = PipelineLoader()

        config = SimpleNamespace(triggers=["go"], confidence=0.75)
        step = loader._build_step("stub_filter", config, {})

        assert isinstance(step, _StubFilter)
        assert step.triggers == ["go"]
        assert step.confidence == 0.75

    def test_service_only(self, _isolated_registry):
        """AgentSwitchExecutor-like: all params from services."""
        register_step("stub_executor", _StubExecutor)
        loader = PipelineLoader()

        fn = MagicMock()
        step = loader._build_step("stub_executor", None, {"switch_fn": fn})

        assert isinstance(step, _StubExecutor)
        assert step.switch_fn is fn

    def test_mixed_config_and_services(self, _isolated_registry):
        """AgentFilter-like: some params from config, some from services."""
        register_step("mixed", _MixedStep)
        loader = PipelineLoader()

        config = SimpleNamespace(triggers=["agente"], match_threshold=0.8)
        services = {"agent_ids": ["a1", "a2"], "subscribe_to_events": True}
        step = loader._build_step("mixed", config, services)

        assert isinstance(step, _MixedStep)
        assert step.agent_ids == ["a1", "a2"]
        assert step.triggers == ["agente"]
        assert step.match_threshold == 0.8
        assert step.subscribe_to_events is True

    def test_default_used_when_param_missing(self, _isolated_registry):
        """Params with defaults are omitted → dataclass uses its own default."""
        register_step("stub_filter", _StubFilter)
        loader = PipelineLoader()

        # Only provide triggers, confidence has default 0.9
        config = SimpleNamespace(triggers=["send"])
        step = loader._build_step("stub_filter", config, {})

        assert step.triggers == ["send"]
        assert step.confidence == 0.9  # dataclass default

    def test_unknown_step_returns_none(self, _isolated_registry, caplog):
        """Unknown step name → None + warning."""
        loader = PipelineLoader()
        with caplog.at_level(logging.WARNING):
            result = loader._build_step("nonexistent", None, {})

        assert result is None
        assert "Unknown pipeline step" in caplog.text


# ---------------------------------------------------------------------------
# 6-8. build_filter_pipeline / build_executor_pipeline
# ---------------------------------------------------------------------------


class TestBuildFilterPipeline:
    def test_disabled_returns_none(self, _isolated_registry):
        config = SimpleNamespace(enabled=False)
        loader = PipelineLoader()
        assert loader.build_filter_pipeline(config) is None

    def test_no_enabled_steps_returns_none(self, _isolated_registry):
        config = SimpleNamespace(
            enabled=True,
            agent_filter=SimpleNamespace(enabled=False),
            submit_filter=SimpleNamespace(enabled=False),
        )
        loader = PipelineLoader()
        assert loader.build_filter_pipeline(config) is None

    def test_with_enabled_steps(self, _isolated_registry):
        register_step("agent_filter", _MixedStep)
        register_step("input_filter", _StubFilter)

        config = SimpleNamespace(
            enabled=True,
            agent_filter=SimpleNamespace(
                enabled=True,
                triggers=["agent"],
                match_threshold=0.6,
            ),
            submit_filter=SimpleNamespace(
                enabled=True,
                triggers=["go"],
                confidence=0.8,
            ),
        )
        services = {"agent_ids": ["a1"], "subscribe_to_events": True}

        loader = PipelineLoader()
        pipeline = loader.build_filter_pipeline(config, services)

        assert pipeline is not None
        assert isinstance(pipeline, Pipeline)
        assert len(pipeline) == 2
        assert pipeline.step_names == ["mixed_step", "stub_filter"]


class TestBuildExecutorPipeline:
    def test_with_switch_fn(self, _isolated_registry):
        register_step("agent_switch", _StubExecutor)

        fn = MagicMock()
        config = SimpleNamespace(enabled=True)
        loader = PipelineLoader()
        pipeline = loader.build_executor_pipeline(config, {"switch_fn": fn})

        assert isinstance(pipeline, Pipeline)
        assert len(pipeline) == 1
        assert pipeline.step_names == ["stub_executor"]


# ---------------------------------------------------------------------------
# 9. Integration: built-in registry has real steps
# ---------------------------------------------------------------------------


class TestBuiltinRegistry:
    def test_builtin_steps_registered(self):
        """Verify the real steps are registered at import time."""
        reg = get_step_registry()
        assert "agent_filter" in reg
        assert "input_filter" in reg
        assert "agent_switch" in reg
        assert "input" in reg
