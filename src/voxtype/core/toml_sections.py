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
#         voxtype agent          (uses default_agent_type)
#
# Set the default agent (optional):
# default_agent_type = "claude"
#
# Define named presets:
# [agent_types.claude]
# command = ["claude"]
# description = "Claude Code (default model)"
#
# [agent_types.sonnet-4.6]
# command = ["claude", "--model", "claude-sonnet-4-6"]
# description = "Claude Sonnet 4.6"
#
# [agent_types.opus-4.6]
# command = ["claude", "--model", "claude-opus-4-6"]
# description = "Claude Opus 4.6"
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


def serialize_section(section: str, config: Config) -> str:
    """Serialize a complex config section as a TOML string with comments."""
    if section == "agent_types":
        return _serialize_agent_types(config)
    elif section == "keyboard.shortcuts":
        return _serialize_shortcuts(config)
    elif section == "audio.sounds":
        return _serialize_sounds(config)
    elif section == "pipeline.submit_filter":
        return _serialize_submit_filter(config)
    elif section == "pipeline.agent_filter":
        return _serialize_agent_filter(config)
    else:
        raise KeyError(section)


def apply_section(section: str, content: str, config_path: Path) -> None:
    """Parse, validate, and save a TOML section to the config file.

    Raises:
        KeyError: Unknown section.
        ValueError: TOML parse error.
        pydantic.ValidationError: Schema validation failure.
    """
    if section == "agent_types":
        _apply_agent_types(content, config_path)
    elif section == "keyboard.shortcuts":
        _apply_shortcuts(content, config_path)
    elif section == "audio.sounds":
        _apply_sounds(content, config_path)
    elif section == "pipeline.submit_filter":
        _apply_submit_filter(content, config_path)
    elif section == "pipeline.agent_filter":
        _apply_agent_filter(content, config_path)
    else:
        raise KeyError(section)


# ---------------------------------------------------------------------------
# agent_types section
# ---------------------------------------------------------------------------


def _serialize_agent_types(config: Config) -> str:
    lines: list[str] = [_AGENT_TYPES_HEADER]

    if config.default_agent_type:
        lines.append(f'default_agent_type = "{config.default_agent_type}"')
        lines.append("")

    for name, at in config.agent_types.items():
        lines.append(f"[agent_types.{name}]")
        # Use JSON-style array (valid TOML inline array)
        cmd_parts = ", ".join(f'"{c}"' for c in at.command)
        lines.append(f"command = [{cmd_parts}]")
        if at.description:
            lines.append(f'description = "{at.description}"')
        lines.append("")

    return "\n".join(lines)


def _apply_agent_types(content: str, config_path: Path) -> None:
    import tomlkit

    from voxtype.config import AgentTypeConfig

    # Parse the submitted TOML
    try:
        doc = tomlkit.parse(content)
    except Exception as exc:
        raise ValueError(f"TOML parse error: {exc}") from exc

    # Validate each agent type entry
    raw_agent_types = dict(doc.get("agent_types", {}))
    validated: dict[str, AgentTypeConfig] = {}
    for name, entry in raw_agent_types.items():
        validated[name] = AgentTypeConfig.model_validate(dict(entry))

    default_agent_type = doc.get("default_agent_type", None)

    # Read existing config file (preserve all other sections)
    if config_path.exists():
        cfg_doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    else:
        cfg_doc = tomlkit.document()
        config_path.parent.mkdir(parents=True, exist_ok=True)

    # Update default_agent_type at top level
    if default_agent_type is not None:
        cfg_doc["default_agent_type"] = default_agent_type
    elif "default_agent_type" in cfg_doc:
        del cfg_doc["default_agent_type"]

    # Remove old agent_types section entirely, then re-add
    if "agent_types" in cfg_doc:
        del cfg_doc["agent_types"]

    if validated:
        agent_types_tbl = tomlkit.table(is_super_table=True)
        for name, at in validated.items():
            entry_tbl = tomlkit.table()
            entry_tbl.add("command", at.command)
            if at.description:
                entry_tbl.add("description", at.description)
            agent_types_tbl.add(name, entry_tbl)
        cfg_doc.add("agent_types", agent_types_tbl)

    config_path.write_text(tomlkit.dumps(cfg_doc), encoding="utf-8")


# ---------------------------------------------------------------------------
# keyboard.shortcuts section
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
        # Show a commented example when no shortcuts are configured
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

    # Parse the submitted TOML
    try:
        doc = tomlkit.parse(content)
    except Exception as exc:
        raise ValueError(f"TOML parse error: {exc}") from exc

    # The shortcuts live under [[keyboard.shortcuts]]
    raw_shortcuts = []
    keyboard_section = doc.get("keyboard", {})
    raw_shortcuts = list(keyboard_section.get("shortcuts", []))

    # Validate each entry
    validated = [ShortcutEntry.model_validate(dict(s)).model_dump(exclude_none=True) for s in raw_shortcuts]

    # Read existing config file (preserve all other sections)
    if config_path.exists():
        cfg_doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    else:
        cfg_doc = tomlkit.document()
        config_path.parent.mkdir(parents=True, exist_ok=True)

    # Update keyboard.shortcuts in the config
    if "keyboard" not in cfg_doc:
        cfg_doc.add("keyboard", tomlkit.table())

    cfg_doc["keyboard"]["shortcuts"] = validated  # type: ignore[index]

    config_path.write_text(tomlkit.dumps(cfg_doc), encoding="utf-8")


# ---------------------------------------------------------------------------
# audio.sounds section
# ---------------------------------------------------------------------------

_SOUNDS_HEADER = """\
# Audio sound effects — played at key events
# Set enabled = false to silence a sound.
# Set path = "/absolute/path/to/file.wav" to use a custom sound.
#
# Available events: start, stop, transcribing, ready, sent, agent_announce
"""


def _serialize_sounds(config: Config) -> str:
    lines: list[str] = [_SOUNDS_HEADER]
    for name, sc in config.audio.sounds.items():
        lines.append(f"[audio.sounds.{name}]")
        lines.append(f"enabled = {str(sc.enabled).lower()}")
        if sc.path:
            lines.append(f'path = "{sc.path}"')
        lines.append("")
    return "\n".join(lines)


def _apply_sounds(content: str, config_path: Path) -> None:
    import tomlkit
    from voxtype.config import SoundConfig

    try:
        doc = tomlkit.parse(content)
    except Exception as exc:
        raise ValueError(f"TOML parse error: {exc}") from exc

    raw_sounds = dict(doc.get("audio", {}).get("sounds", {}))
    validated: dict = {}
    for name, entry in raw_sounds.items():
        validated[name] = SoundConfig.model_validate(dict(entry)).model_dump(exclude_none=True)

    if config_path.exists():
        cfg_doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    else:
        cfg_doc = tomlkit.document()
        config_path.parent.mkdir(parents=True, exist_ok=True)

    if "audio" not in cfg_doc:
        cfg_doc.add("audio", tomlkit.table())

    sounds_tbl = tomlkit.table(is_super_table=True)
    for name, sc in validated.items():
        entry_tbl = tomlkit.table()
        entry_tbl.add("enabled", sc["enabled"])
        if sc.get("path"):
            entry_tbl.add("path", sc["path"])
        sounds_tbl.add(name, entry_tbl)

    cfg_doc["audio"]["sounds"] = sounds_tbl  # type: ignore[index]
    config_path.write_text(tomlkit.dumps(cfg_doc), encoding="utf-8")


# ---------------------------------------------------------------------------
# pipeline.submit_filter section
# ---------------------------------------------------------------------------

_SUBMIT_FILTER_HEADER = """\
# Submit filter — detects voice trigger phrases to submit text
# Triggers are grouped by language code (en, it, es, de, fr, ...).
# Each trigger is a list of word sequences (alternatives).
#
# [pipeline.submit_filter.triggers]
# en = [["ok", "send"], ["ok", "submit"], ["go", "ahead"]]
# it = [["ok", "invia"], ["ok", "manda"]]
"""


def _serialize_submit_filter(config: Config) -> str:
    sf = config.pipeline.submit_filter
    lines: list[str] = [_SUBMIT_FILTER_HEADER]
    lines.append(f"enabled = {str(sf.enabled).lower()}")
    lines.append(f"confidence_threshold = {sf.confidence_threshold}")
    lines.append(f"max_scan_words = {sf.max_scan_words}")
    lines.append(f"decay_rate = {sf.decay_rate}")
    lines.append("")
    lines.append("[pipeline.submit_filter.triggers]")
    for lang, phrases in sf.triggers.items():
        inner = ", ".join(
            "[" + ", ".join(f'"{w}"' for w in phrase) + "]"
            for phrase in phrases
        )
        lines.append(f"{lang} = [{inner}]")
    return "\n".join(lines)


def _apply_submit_filter(content: str, config_path: Path) -> None:
    import tomlkit
    from voxtype.config import SubmitFilterConfig

    try:
        doc = tomlkit.parse(content)
    except Exception as exc:
        raise ValueError(f"TOML parse error: {exc}") from exc

    raw = dict(doc.get("pipeline", {}).get("submit_filter", {}))
    validated = SubmitFilterConfig.model_validate(raw)

    if config_path.exists():
        cfg_doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    else:
        cfg_doc = tomlkit.document()
        config_path.parent.mkdir(parents=True, exist_ok=True)

    if "pipeline" not in cfg_doc:
        cfg_doc.add("pipeline", tomlkit.table())

    sf_tbl = tomlkit.table()
    sf_tbl.add("enabled", validated.enabled)
    sf_tbl.add("confidence_threshold", validated.confidence_threshold)
    sf_tbl.add("max_scan_words", validated.max_scan_words)
    sf_tbl.add("decay_rate", validated.decay_rate)
    if validated.triggers:
        triggers_tbl = tomlkit.table()
        for lang, phrases in validated.triggers.items():
            triggers_tbl.add(lang, [list(p) for p in phrases])
        sf_tbl.add("triggers", triggers_tbl)

    cfg_doc["pipeline"]["submit_filter"] = sf_tbl  # type: ignore[index]
    config_path.write_text(tomlkit.dumps(cfg_doc), encoding="utf-8")


# ---------------------------------------------------------------------------
# pipeline.agent_filter section
# ---------------------------------------------------------------------------

_AGENT_FILTER_HEADER = """\
# Agent filter — voice-controlled agent switching
# Say a trigger word followed by the agent name to switch.
# Example: "agent claude", "agent sonnet"
#
# triggers = ["agent"]    # words that precede the agent name
# match_threshold = 0.5   # fuzzy match score (0.0 = loose, 1.0 = exact)
"""


def _serialize_agent_filter(config: Config) -> str:
    af = config.pipeline.agent_filter
    triggers_str = "[" + ", ".join(f'"{t}"' for t in af.triggers) + "]"
    lines: list[str] = [_AGENT_FILTER_HEADER]
    lines.append(f"enabled = {str(af.enabled).lower()}")
    lines.append(f"match_threshold = {af.match_threshold}")
    lines.append(f"triggers = {triggers_str}")
    return "\n".join(lines)


def _apply_agent_filter(content: str, config_path: Path) -> None:
    import tomlkit
    from voxtype.config import AgentFilterConfig

    try:
        doc = tomlkit.parse(content)
    except Exception as exc:
        raise ValueError(f"TOML parse error: {exc}") from exc

    raw = dict(doc.get("pipeline", {}).get("agent_filter", {}))
    validated = AgentFilterConfig.model_validate(raw)

    if config_path.exists():
        cfg_doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    else:
        cfg_doc = tomlkit.document()
        config_path.parent.mkdir(parents=True, exist_ok=True)

    if "pipeline" not in cfg_doc:
        cfg_doc.add("pipeline", tomlkit.table())

    af_tbl = tomlkit.table()
    af_tbl.add("enabled", validated.enabled)
    af_tbl.add("match_threshold", validated.match_threshold)
    af_tbl.add("triggers", validated.triggers)

    cfg_doc["pipeline"]["agent_filter"] = af_tbl  # type: ignore[index]
    config_path.write_text(tomlkit.dumps(cfg_doc), encoding="utf-8")
