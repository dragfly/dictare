"""Plugin system for voxtype.

Plugins can be discovered from:
1. Built-in plugins (in this package)
2. Entry points (voxtype.plugins group)
3. User plugins (~/.config/voxtype/plugins/)
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from voxtype.plugins.base import BasePlugin, Plugin

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "BasePlugin",
    "Plugin",
    "discover_plugins",
    "get_user_plugins_dir",
]

def get_user_plugins_dir() -> Path:
    """Get user plugins directory.

    Returns:
        Path to ~/.config/voxtype/plugins/
    """
    return Path.home() / ".config" / "voxtype" / "plugins"

def _discover_builtin_plugins() -> Iterator[type[Plugin]]:
    """Discover built-in plugins."""
    # Built-in plugins will be added here
    return iter([])

def _discover_entrypoint_plugins() -> Iterator[type[Plugin]]:
    """Discover plugins from entry points.

    Entry points are defined in pyproject.toml:
    [project.entry-points."voxtype.plugins"]
    my_plugin = "my_package:MyPlugin"
    """
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="voxtype.plugins")

        for ep in eps:
            try:
                plugin_cls = ep.load()
                if isinstance(plugin_cls, type) and issubclass(plugin_cls, Plugin):
                    yield plugin_cls
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(
                    f"Failed to load plugin '{ep.name}': {e}"
                )
    except Exception:
        # importlib.metadata not available or other error
        return

def _discover_user_plugins() -> Iterator[type[Plugin]]:
    """Discover user plugins from ~/.config/voxtype/plugins/.

    Each plugin should be a Python file or directory with a Plugin class.
    """
    plugins_dir = get_user_plugins_dir()
    if not plugins_dir.exists():
        return

    for item in plugins_dir.iterdir():
        try:
            plugin_cls = _load_user_plugin(item)
            if plugin_cls is not None:
                yield plugin_cls
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(
                f"Failed to load user plugin '{item.name}': {e}"
            )

def _load_user_plugin(path: Path) -> type[Plugin] | None:
    """Load a user plugin from a file or directory.

    Args:
        path: Path to plugin file (.py) or directory (with __init__.py).

    Returns:
        Plugin class or None if not found.
    """
    # Determine module file
    if path.is_file() and path.suffix == ".py":
        module_file = path
        module_name = f"voxtype_user_plugin_{path.stem}"
    elif path.is_dir() and (path / "__init__.py").exists():
        module_file = path / "__init__.py"
        module_name = f"voxtype_user_plugin_{path.name}"
    else:
        return None

    # Load module
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    # Find Plugin class
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and attr is not Plugin
            and attr is not BasePlugin
            and issubclass(attr, Plugin)
        ):
            return attr

    return None

def discover_plugins() -> list[type[Plugin]]:
    """Discover all available plugins.

    Discovery order:
    1. Built-in plugins
    2. Entry point plugins
    3. User plugins

    Returns:
        List of plugin classes.
    """
    plugins: list[type[Plugin]] = []
    seen_names: set[str] = set()

    for source in [
        _discover_builtin_plugins,
        _discover_entrypoint_plugins,
        _discover_user_plugins,
    ]:
        for plugin_cls in source():
            # Skip duplicates by name
            try:
                plugin = plugin_cls()
                if plugin.name not in seen_names:
                    plugins.append(plugin_cls)
                    seen_names.add(plugin.name)
            except Exception:
                continue

    return plugins
