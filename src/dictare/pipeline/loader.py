"""Plugin loader for pipeline steps.

Uses inspect.signature() to auto-inject dependencies (config attrs + runtime
services) into step constructors — pluggy-style DI without pluggy.

Usage:
    loader = PipelineLoader()
    pipeline = loader.build_filter_pipeline(config.pipeline, services)
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field

from dictare.pipeline.base import Executor, Filter, Pipeline

logger = logging.getLogger(__name__)

# Global registry: name -> step class
_BUILTIN_STEPS: dict[str, type] = {}


def register_step(name: str, cls: type) -> None:
    """Register a pipeline step class by name."""
    _BUILTIN_STEPS[name] = cls


def get_step_registry() -> dict[str, type]:
    """Return a copy of the step registry."""
    return _BUILTIN_STEPS.copy()


@dataclass
class PipelineLoader:
    """Builds pipelines from config using DI-based step construction.

    The loader resolves constructor parameters by inspecting each step's
    ``__init__`` signature and matching params against ``services`` (runtime
    deps like switch_fn) and ``config`` attributes (triggers, thresholds).

    Attributes:
        registry: Step name -> class mapping. Defaults to global registry.
    """

    registry: dict[str, type] = field(default_factory=get_step_registry)

    def build_filter_pipeline(
        self,
        pipeline_config: object,
        services: dict | None = None,
    ) -> Pipeline | None:
        """Build the filter pipeline from config.

        Args:
            pipeline_config: PipelineConfig with ``enabled``, ``agent_filter``,
                ``submit_filter`` attributes.
            services: Runtime services dict (e.g. agent_ids, subscribe_to_events).

        Returns:
            Pipeline if enabled and has steps, None otherwise.
        """
        if not getattr(pipeline_config, "enabled", False):
            return None

        services = services or {}
        pipeline = Pipeline()

        # Mute filter (must run FIRST — discards all text when muted)
        mute_cfg = getattr(pipeline_config, "mute_filter", None)
        if mute_cfg and getattr(mute_cfg, "enabled", False):
            step = self._build_step("mute_filter", mute_cfg, services)
            if step is not None:
                pipeline.add_step(step)

        # Agent filter
        agent_cfg = getattr(pipeline_config, "agent_filter", None)
        if agent_cfg and getattr(agent_cfg, "enabled", False):
            step = self._build_step("agent_filter", agent_cfg, services)
            if step is not None:
                pipeline.add_step(step)

        # Input/submit filter
        submit_cfg = getattr(pipeline_config, "submit_filter", None)
        if submit_cfg and getattr(submit_cfg, "enabled", False):
            step = self._build_step("input_filter", submit_cfg, services)
            if step is not None:
                pipeline.add_step(step)

        return pipeline if len(pipeline) > 0 else None

    def build_executor_pipeline(
        self,
        pipeline_config: object,
        services: dict | None = None,
    ) -> Pipeline:
        """Build the executor pipeline from config.

        Args:
            pipeline_config: PipelineConfig (unused for now, executors are
                always enabled).
            services: Runtime services dict (e.g. switch_fn).

        Returns:
            Pipeline with executor steps.
        """
        services = services or {}
        pipeline = Pipeline()

        step = self._build_step("mute", None, services)
        if step is not None:
            pipeline.add_step(step)

        step = self._build_step("agent_switch", None, services)
        if step is not None:
            pipeline.add_step(step)

        return pipeline

    def _build_step(
        self,
        name: str,
        step_config: object | None,
        services: dict,
    ) -> Filter | Executor | None:
        """Build a single step by inspecting its constructor.

        Resolution order for each parameter:
        1. ``services`` dict
        2. Attribute of ``step_config``
        3. Parameter default (omitted — dataclass uses its own default)

        Args:
            name: Registered step name.
            step_config: Config object whose attributes map to constructor params.
            services: Runtime services dict.

        Returns:
            Instantiated step, or None if name not in registry.
        """
        cls = self.registry.get(name)
        if cls is None:
            logger.warning("Unknown pipeline step: %s", name)
            return None

        sig = inspect.signature(cls)
        kwargs: dict = {}
        missing: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # 1. Services take priority
            if param_name in services:
                kwargs[param_name] = services[param_name]
            # 2. Config attribute
            elif step_config is not None and hasattr(step_config, param_name):
                kwargs[param_name] = getattr(step_config, param_name)
            # 3. Has default → omit, let the class use its default
            elif param.default is not inspect.Parameter.empty:
                continue
            elif param.default is inspect.Parameter.empty and _has_dataclass_default(cls, param_name):
                continue
            else:
                missing.append(param_name)

        if missing:
            logger.debug(
                "Skipping step '%s': unresolved params %s", name, missing,
            )
            return None

        return cls(**kwargs)


def _has_dataclass_default(cls: type, param_name: str) -> bool:
    """Check if a dataclass field has a default value."""
    import dataclasses

    if not dataclasses.is_dataclass(cls):
        return False

    for f in dataclasses.fields(cls):
        if f.name == param_name:
            return (
                f.default is not dataclasses.MISSING
                or f.default_factory is not dataclasses.MISSING
            )
    return False
