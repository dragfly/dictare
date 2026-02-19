"""TOML section serialization/deserialization for the settings UI editor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxtype.config import Config

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SUPPORTED_SECTIONS = frozenset([
    "agent_types",
    "keyboard.shortcuts",
    "audio.sounds",
    "pipeline.submit_filter",
    "pipeline.agent_filter",
])

_AGENT_TYPES_HEADER = """\
# Agent type presets — single-command launch
# Usage:  voxtype agent <name>
#         voxtype agent <name> --continue   (continue previous session)
#         voxtype agent                     (uses default_agent_type)
#
# continue_args: args inserted after argv[0] when --continue/-C is passed.
#   Claude Code uses ["-c"], Codex uses ["--resume"], Aider has no continue flag.
#
# Set the default agent (optional):
# default_agent_type = "claude"
#
# Define named presets:
# [agent_types.claude]
# command = ["claude"]
# continue_args = ["-c"]
# description = "Claude Code (default model)"
#
# [agent_types."sonnet-4.6"]
# command = ["claude", "--model", "claude-sonnet-4-6"]
# continue_args = ["-c"]
# description = "Claude Sonnet 4.6"
#
# [agent_types.aider]
# command = ["aider", "--model", "claude-sonnet-4-5"]
# description = "Aider with Claude Sonnet"
"""

_SHORTCUTS_HEADER = """\
# Keyboard shortcuts — trigger voice commands with key combinations
# Each shortcut is a [[keyboard.shortcuts]] entry.
#
# Available commands:
#   toggle-listening   — start/stop listening
#   switch-mode        — toggle keyboard ↔ agent output mode
#   repeat             — re-type the last transcription
#   clear              — clear last transcription
#   cancel             — cancel current action
#   next-agent         — cycle to next agent
#   prev-agent         — cycle to previous agent
#
# Example:
# [[keyboard.shortcuts]]
# keys = "ctrl+shift+l"
# command = "toggle-listening"
#
# [[keyboard.shortcuts]]
# keys = "ctrl+shift+m"
# command = "switch-mode"
"""

_SOUNDS_HEADER = """\
# Audio sound effects — played at key events
# Set enabled = false to silence a sound.
# Set path = "/absolute/path/to/file.wav" to use a custom sound.
#
# Available events: start, stop, transcribing, ready, sent, agent_announce
"""

_SUBMIT_FILTER_HEADER = """\
# Submit filter — detects voice trigger phrases to submit text
# Triggers are grouped by language code (en, it, es, de, fr, ...).
# Each trigger is a list of word sequences (alternatives).
#
# [pipeline.submit_filter.triggers]
# en = [["ok", "send"], ["ok", "submit"], ["go", "ahead"]]
# it = [["ok", "invia"], ["ok", "manda"]]
"""

_AGENT_FILTER_HEADER = """\
# Agent filter — voice-controlled agent switching
# Say a trigger word followed by the agent name to switch.
# Example: "agent claude", "agent sonnet"
#
# triggers = ["agent"]    # words that precede the agent name
# match_threshold = 0.5   # fuzzy match score (0.0 = loose, 1.0 = exact)
"""

# Registry for generic sections: section → (dotted_path, header, model_class_name, is_dict_of_models)
_GENERIC_SECTIONS: dict[str, tuple[str, str, str, bool]] = {
    "audio.sounds": ("audio.sounds", _SOUNDS_HEADER, "SoundConfig", True),
    "pipeline.submit_filter": ("pipeline.submit_filter", _SUBMIT_FILTER_HEADER, "SubmitFilterConfig", False),
    "pipeline.agent_filter": ("pipeline.agent_filter", _AGENT_FILTER_HEADER, "AgentFilterConfig", False),
}


def serialize_section(section: str, config: Config) -> str:
    """Serialize a complex config section as a TOML string with comments."""
    if section == "agent_types":
        return _serialize_agent_types(config)
    if section == "keyboard.shortcuts":
        return _serialize_shortcuts(config)
    meta = _GENERIC_SECTIONS.get(section)
    if meta is None:
        raise KeyError(section)
    dotted_path, header, _, _ = meta
    return _serialize_pydantic_section(dotted_path, config, header)


def apply_section(section: str, content: str, config_path: Path) -> None:
    """Parse, validate, and save a TOML section to the config file.

    Raises:
        KeyError: Unknown section.
        ValueError: TOML parse error.
        pydantic.ValidationError: Schema validation failure.
    """
    if section == "agent_types":
        _apply_agent_types(content, config_path)
        return
    if section == "keyboard.shortcuts":
        _apply_shortcuts(content, config_path)
        return
    meta = _GENERIC_SECTIONS.get(section)
    if meta is None:
        raise KeyError(section)
    dotted_path, _, model_cls_name, is_dict = meta
    _apply_pydantic_section(dotted_path, model_cls_name, is_dict, content, config_path)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _navigate_config(config: Config, dotted_path: str):
    """Navigate config object following a dotted attribute path."""
    obj = config
    for part in dotted_path.split("."):
        obj = getattr(obj, part)
    return obj


def _make_toml_table(data: dict, is_super_table: bool = False):
    """Convert a plain dict to a tomlkit table (block style)."""
    import tomlkit
    tbl = tomlkit.table(is_super_table=is_super_table)
    for k, v in data.items():
        if isinstance(v, dict):
            tbl.add(k, _make_toml_table(v))
        else:
            tbl.add(k, v)
    return tbl


def _set_nested_table(parent, parts: list[str], data: dict) -> None:
    """Recursively add a nested tomlkit table at the given path."""
    import tomlkit
    if len(parts) == 1:
        is_super = isinstance(data, dict) and bool(data) and all(isinstance(v, dict) for v in data.values())
        parent.add(parts[0], _make_toml_table(data, is_super_table=is_super))
    else:
        super_tbl = tomlkit.table(is_super_table=True)
        _set_nested_table(super_tbl, parts[1:], data)
        parent.add(parts[0], super_tbl)


def _serialize_pydantic_section(dotted_path: str, config: Config, header: str) -> str:
    """Generic serializer: navigate config, dump as TOML under the dotted path."""
    import tomlkit

    obj = _navigate_config(config, dotted_path)
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(exclude_none=True)
    elif isinstance(obj, dict):
        data = {
            k: (v.model_dump(exclude_none=True) if hasattr(v, "model_dump") else v)
            for k, v in obj.items()
        }
    else:
        return header

    doc = tomlkit.document()
    _set_nested_table(doc, dotted_path.split("."), data)
    return header + tomlkit.dumps(doc)


def _apply_pydantic_section(
    dotted_path: str,
    model_cls_name: str,
    is_dict_of_models: bool,
    content: str,
    config_path: Path,
) -> None:
    """Generic apply: parse TOML, validate with Pydantic, write section to config."""
    import importlib

    import tomlkit

    try:
        doc = tomlkit.parse(content)
    except Exception as exc:
        raise ValueError(f"TOML parse error: {exc}") from exc

    # Extract value at dotted path
    raw = doc
    for part in dotted_path.split("."):
        raw = raw.get(part, {})

    model_cls = getattr(importlib.import_module("voxtype.config"), model_cls_name)
    if is_dict_of_models:
        validated: dict = {
            k: model_cls.model_validate(dict(v)).model_dump(exclude_none=True)
            for k, v in dict(raw).items()
        }
    else:
        validated = model_cls.model_validate(dict(raw)).model_dump(exclude_none=True)

    # Load existing config (preserve all other sections)
    if config_path.exists():
        cfg_doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    else:
        cfg_doc = tomlkit.document()
        config_path.parent.mkdir(parents=True, exist_ok=True)

    # Navigate to parent section and update the leaf key
    parts = dotted_path.split(".")
    parent = cfg_doc
    for part in parts[:-1]:
        if part not in parent:
            parent.add(part, tomlkit.table())
        parent = parent[part]

    parent[parts[-1]] = validated
    config_path.write_text(tomlkit.dumps(cfg_doc), encoding="utf-8")


# ---------------------------------------------------------------------------
# agent_types section (special: default_agent_type at top level + nested tables)
# ---------------------------------------------------------------------------


def _serialize_agent_types(config: Config) -> str:
    lines: list[str] = [_AGENT_TYPES_HEADER]

    if config.default_agent_type:
        lines.append(f'default_agent_type = "{config.default_agent_type}"')
        lines.append("")

    for name, at in config.agent_types.items():
        quoted = f'"{name}"' if "." in name else name
        lines.append(f"[agent_types.{quoted}]")
        cmd_parts = ", ".join(f'"{c}"' for c in at.command)
        lines.append(f"command = [{cmd_parts}]")
        if at.continue_args:
            ca_parts = ", ".join(f'"{c}"' for c in at.continue_args)
            lines.append(f"continue_args = [{ca_parts}]")
        if at.description:
            lines.append(f'description = "{at.description}"')
        lines.append("")

    return "\n".join(lines)


def _apply_agent_types(content: str, config_path: Path) -> None:
    import tomlkit

    from voxtype.config import AgentTypeConfig

    try:
        doc = tomlkit.parse(content)
    except Exception as exc:
        raise ValueError(f"TOML parse error: {exc}") from exc

    raw_agent_types = dict(doc.get("agent_types", {}))
    validated: dict[str, AgentTypeConfig] = {}
    for name, entry in raw_agent_types.items():
        validated[name] = AgentTypeConfig.model_validate(dict(entry))

    default_agent_type = doc.get("default_agent_type", None)

    if config_path.exists():
        cfg_doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    else:
        cfg_doc = tomlkit.document()
        config_path.parent.mkdir(parents=True, exist_ok=True)

    if default_agent_type is not None:
        cfg_doc["default_agent_type"] = default_agent_type
    elif "default_agent_type" in cfg_doc:
        del cfg_doc["default_agent_type"]

    if "agent_types" in cfg_doc:
        del cfg_doc["agent_types"]

    if validated:
        agent_types_tbl = tomlkit.table(is_super_table=True)
        for name, at in validated.items():
            entry_tbl = tomlkit.table()
            entry_tbl.add("command", at.command)
            if at.continue_args:
                entry_tbl.add("continue_args", at.continue_args)
            if at.description:
                entry_tbl.add("description", at.description)
            agent_types_tbl.add(name, entry_tbl)
        cfg_doc.add("agent_types", agent_types_tbl)

    config_path.write_text(tomlkit.dumps(cfg_doc), encoding="utf-8")


# ---------------------------------------------------------------------------
# keyboard.shortcuts section (special: [[array.of.tables]] syntax)
# ---------------------------------------------------------------------------


def _serialize_shortcuts(config: Config) -> str:
    lines: list[str] = [_SHORTCUTS_HEADER]

    shortcuts = config.keyboard.shortcuts
    if shortcuts:
        for shortcut in shortcuts:
            lines.append("[[keyboard.shortcuts]]")
            lines.append(f'keys = "{shortcut.get("keys", "")}"')
            lines.append(f'command = "{shortcut.get("command", "")}"')
            if "args" in shortcut and shortcut["args"]:
                args_json = json.dumps(shortcut["args"])
                lines.append(f"args = {args_json}")
            lines.append("")
    else:
        lines.append("# [[keyboard.shortcuts]]")
        lines.append('# keys = "ctrl+shift+l"')
        lines.append('# command = "toggle-listening"')

    return "\n".join(lines)


def _apply_shortcuts(content: str, config_path: Path) -> None:
    import tomlkit
    from pydantic import BaseModel, field_validator

    class ShortcutEntry(BaseModel):
        keys: str
        command: str
        args: dict = {}

        @field_validator("keys")
        @classmethod
        def keys_not_empty(cls, v: str) -> str:
            if not v.strip():
                raise ValueError("keys must not be empty")
            return v

        @field_validator("command")
        @classmethod
        def command_not_empty(cls, v: str) -> str:
            if not v.strip():
                raise ValueError("command must not be empty")
            return v

    try:
        doc = tomlkit.parse(content)
    except Exception as exc:
        raise ValueError(f"TOML parse error: {exc}") from exc

    keyboard_section = doc.get("keyboard", {})
    raw_shortcuts = list(keyboard_section.get("shortcuts", []))
    validated = [ShortcutEntry.model_validate(dict(s)).model_dump(exclude_none=True) for s in raw_shortcuts]

    if config_path.exists():
        cfg_doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    else:
        cfg_doc = tomlkit.document()
        config_path.parent.mkdir(parents=True, exist_ok=True)

    if "keyboard" not in cfg_doc:
        cfg_doc.add("keyboard", tomlkit.table())

    cfg_doc["keyboard"]["shortcuts"] = validated  # type: ignore[index]

    config_path.write_text(tomlkit.dumps(cfg_doc), encoding="utf-8")
