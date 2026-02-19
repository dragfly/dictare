"""TOML section serialization/deserialization for the settings UI editor.

Design: WYSIWYG + validation.
- Fetch: read raw text from the config file (preserves user formatting and comments).
         Falls back to a comment-only template when the section is absent.
- Save:  validate structure with Pydantic; write the user's literal text verbatim.
         The config file is never regenerated from the model.
"""

from __future__ import annotations

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
#
# Advanced audio settings (sample_rate, channels, device, pre_buffer_ms,
# min_speech_ms, transcribing_sound_min_ms) live in [audio] in config.toml.
# Edit them with: voxtype config edit
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

_SECTION_HEADERS: dict[str, str] = {
    "agent_types": _AGENT_TYPES_HEADER,
    "keyboard.shortcuts": _SHORTCUTS_HEADER,
    "audio.sounds": _SOUNDS_HEADER,
    "pipeline.submit_filter": _SUBMIT_FILTER_HEADER,
    "pipeline.agent_filter": _AGENT_FILTER_HEADER,
}

def serialize_section(section: str, config: Config) -> str:  # noqa: ARG001
    """Return the TOML text for a section.

    Reads raw text from the config file when the section exists (WYSIWYG).
    Falls back to a comment-only template when the section is absent.

    The ``config`` parameter is unused but kept for API compatibility.
    """
    from voxtype.config import get_config_path

    if section not in SUPPORTED_SECTIONS:
        raise KeyError(section)

    raw = _fetch_section_raw(section, get_config_path())
    if raw is not None:
        return raw

    return _SECTION_HEADERS[section]

def apply_section(section: str, content: str, config_path: Path) -> None:
    """Validate the TOML section then write the user's literal text to the config file.

    Raises:
        KeyError: Unknown section.
        ValueError: TOML parse error.
        pydantic.ValidationError: Schema validation failure.
    """
    if section not in SUPPORTED_SECTIONS:
        raise KeyError(section)

    _validate_section(section, content)
    _write_section_raw(section, content, config_path)

# ---------------------------------------------------------------------------
# WYSIWYG fetch — read raw section lines from file
# ---------------------------------------------------------------------------

def _fetch_section_raw(section: str, config_path: Path) -> str | None:
    """Extract the raw TOML text for a section from the config file.

    Uses a line scanner on the raw file text so that all user comments, blank
    lines, and formatting are preserved exactly as written.
    Returns None if the section is absent from the file.
    """
    if not config_path.exists():
        return None

    try:
        text = config_path.read_text(encoding="utf-8")
    except Exception:
        return None

    return _extract_section_lines(text, section)

def _extract_section_lines(text: str, section: str) -> str | None:
    """Scan TOML text line by line and return lines owned by ``section``.

    Owned lines:
    - Top-level keys belonging to the section (e.g. ``default_agent_type``).
    - All ``[section.*]`` / ``[[section.*]]`` headers and their content.
    - Comment and blank lines immediately preceding an owned header (flushed
      when the header is found; discarded when a non-owned header appears).
    """
    # (owned_header_prefixes, owned_toplevel_keys)
    owned_map: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {
        "agent_types": (
            ("[agent_types", '["agent_types'),
            frozenset({"default_agent_type"}),
        ),
        "keyboard.shortcuts": (
            ("[[keyboard.shortcuts",),
            frozenset(),
        ),
        "audio.sounds": (
            ("[audio.sounds",),
            frozenset(),
        ),
        "pipeline.submit_filter": (
            ("[pipeline.submit_filter",),
            frozenset(),
        ),
        "pipeline.agent_filter": (
            ("[pipeline.agent_filter",),
            frozenset(),
        ),
    }

    if section not in owned_map:
        return None

    owned_prefixes, owned_toplevel = owned_map[section]
    result: list[str] = []
    has_content = False
    in_target = False
    comment_buf: list[str] = []  # comments/blanks that might precede an owned header

    for line in text.splitlines(keepends=True):
        stripped = line.strip()

        if stripped.startswith("["):
            is_owned = any(stripped.startswith(p) for p in owned_prefixes)
            if is_owned:
                # Flush buffered comments — they belong to this owned section
                result.extend(comment_buf)
                comment_buf = []
                result.append(line)
                in_target = True
                has_content = True
            else:
                # Non-owned section: discard buffer, leave owned section
                comment_buf = []
                in_target = False

        elif in_target:
            result.append(line)

        elif owned_toplevel and stripped and any(
            stripped.startswith(k) for k in owned_toplevel
        ):
            # Top-level owned key (e.g. default_agent_type) outside any section header
            result.extend(comment_buf)
            comment_buf = []
            result.append(line)
            has_content = True

        elif not stripped or stripped.startswith("#"):
            # Comment or blank — may precede an owned section header
            comment_buf.append(line)

        else:
            # Other content: discard accumulated comments
            comment_buf = []

    if not has_content:
        return None

    return "".join(result).strip() + "\n"

# ---------------------------------------------------------------------------
# WYSIWYG write — remove owned keys, append user's literal text
# ---------------------------------------------------------------------------

def _write_section_raw(section: str, user_content: str, config_path: Path) -> None:
    """Remove the section's owned keys from the config, then append the user's text."""
    import tomlkit

    if config_path.exists():
        cfg_doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    else:
        cfg_doc = tomlkit.document()
        config_path.parent.mkdir(parents=True, exist_ok=True)

    if section == "agent_types":
        for key in ("agent_types", "default_agent_type"):
            if key in cfg_doc:
                del cfg_doc[key]

    elif section == "keyboard.shortcuts":
        if "keyboard" in cfg_doc:
            kb = cfg_doc["keyboard"]
            if "shortcuts" in kb:
                del kb["shortcuts"]  # type: ignore[attr-defined]
            if not dict(kb):
                del cfg_doc["keyboard"]

    else:
        # Dotted path: audio.sounds, pipeline.submit_filter, pipeline.agent_filter
        parts = section.split(".")
        parent: object = cfg_doc
        for part in parts[:-1]:
            if not hasattr(parent, "__contains__") or part not in parent:  # type: ignore[operator]
                parent = None
                break
            parent = parent[part]  # type: ignore[index]
        if parent is not None and parts[-1] in parent:  # type: ignore[operator]
            del parent[parts[-1]]  # type: ignore[attr-defined]

    remaining = tomlkit.dumps(cfg_doc).rstrip("\n")
    user_text = user_content.strip()
    separator = "\n\n" if remaining.strip() else ""
    config_path.write_text(remaining + separator + user_text + "\n", encoding="utf-8")

# ---------------------------------------------------------------------------
# Validation — Pydantic schema checks, no file I/O
# ---------------------------------------------------------------------------

def _validate_section(section: str, content: str) -> None:
    """Parse and validate section content. Raises ValueError or ValidationError."""
    import tomlkit

    try:
        doc = tomlkit.parse(content)
    except Exception as exc:
        raise ValueError(f"TOML parse error: {exc}") from exc

    if section == "agent_types":
        from voxtype.config import AgentTypeConfig

        for _name, entry in dict(doc.get("agent_types", {})).items():
            AgentTypeConfig.model_validate(dict(entry))

    elif section == "keyboard.shortcuts":
        from pydantic import BaseModel, field_validator

        class _Shortcut(BaseModel):
            keys: str
            command: str
            args: dict = {}

            @field_validator("keys", "command")
            @classmethod
            def not_empty(cls, v: str) -> str:
                if not v.strip():
                    raise ValueError("must not be empty")
                return v

        keyboard = doc.get("keyboard") or {}
        for s in list(keyboard.get("shortcuts", [])):
            _Shortcut.model_validate(dict(s))

    elif section == "audio.sounds":
        from voxtype.config import SoundConfig

        audio = doc.get("audio") or {}
        for _k, v in dict(audio.get("sounds", {})).items():
            SoundConfig.model_validate(dict(v))

    elif section == "pipeline.submit_filter":
        from voxtype.config import SubmitFilterConfig

        pipeline = doc.get("pipeline") or {}
        raw = pipeline.get("submit_filter") or {}
        SubmitFilterConfig.model_validate(dict(raw))

    elif section == "pipeline.agent_filter":
        from voxtype.config import AgentFilterConfig

        pipeline = doc.get("pipeline") or {}
        raw = pipeline.get("agent_filter") or {}
        AgentFilterConfig.model_validate(dict(raw))
