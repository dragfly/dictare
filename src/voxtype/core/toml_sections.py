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
    "audio.advanced",
    "audio.sounds",
    "stt.advanced",
    "pipeline.submit_filter",
    "pipeline.agent_filter",
])

_AGENT_TYPES_HEADER = """\
# Agent type presets — single-command launch
# Usage:  voxtype agent <name>
#         voxtype agent <name> --continue   (continue previous session)
#         voxtype agent                     (uses agent_types.default)
#
# continue_args: args inserted after argv[0] when --continue/-C is passed.
#   Claude Code uses ["-c"], Codex uses ["--resume"], Aider has no continue flag.
#
# [agent_types]
# default = "claude"       # optional: used when no --type is given
#
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

_AUDIO_ADVANCED_HEADER = """\
[audio.advanced]
# sample_rate = 16000               # Sample rate in Hz (Whisper requires 16000)
# channels = 1                      # Number of audio channels
# device = ""                       # Audio device name (empty = system default)
# pre_buffer_ms = 640               # Audio captured before VAD triggers (ms)
# min_speech_ms = 150               # Min speech duration before VAD activates (ms)
# transcribing_sound_min_ms = 8000  # Min audio length (ms) to trigger typewriter sound
"""

_STT_ADVANCED_HEADER = """\
[stt.advanced]
# device = "auto"                # auto, cpu, cuda, mlx
# compute_type = "int8"         # int8 (fastest), float16, float32 (most accurate)
# beam_size = 5                 # Higher = slower but more accurate
# hotwords = ""                 # Boost recognition: "voxtype,joshua" (turbo model only)
# max_repetitions = 5           # Anti-hallucination: max consecutive repeats
"""

_SOUNDS_HEADER = """\
# Sound effects — set enabled = false to silence, path = "/abs/path.wav" for custom file.
# Default bundled files: start/sent = up-beep.wav, stop = down-beep.wav,
#                        transcribing = typewriter.wav, ready = ready.wav,
#                        agent_announce = (TTS speech, no sound file)

[audio.sounds.start]               # OFF → LISTENING
enabled = true
# path = ""                        # up-beep.wav

[audio.sounds.stop]                # LISTENING → OFF
enabled = true
# path = ""                        # down-beep.wav

[audio.sounds.transcribing]        # LISTENING → TRANSCRIBING (typewriter loop)
enabled = true
# path = ""                        # typewriter.wav

[audio.sounds.ready]               # TRANSCRIBING → LISTENING (carriage return)
enabled = true
# path = ""                        # ready.wav

[audio.sounds.sent]                # Text sent
enabled = true
# path = ""                        # up-beep.wav

[audio.sounds.agent_announce]      # TTS announces agent name on switch
enabled = true
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
    "audio.advanced": _AUDIO_ADVANCED_HEADER,
    "audio.sounds": _SOUNDS_HEADER,
    "stt.advanced": _STT_ADVANCED_HEADER,
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
    - All ``[section.*]`` / ``[[section.*]]`` headers and their content.
    - Comment and blank lines immediately preceding an owned header (flushed
      when the header is found; discarded when a non-owned header appears).
    """
    owned_map: dict[str, tuple[str, ...]] = {
        "agent_types": ("[agent_types",),
        "keyboard.shortcuts": ("[[keyboard.shortcuts",),
        "audio.advanced": ("[audio.advanced",),
        "audio.sounds": ("[audio.sounds",),
        "stt.advanced": ("[stt.advanced",),
        "pipeline.submit_filter": ("[pipeline.submit_filter",),
        "pipeline.agent_filter": ("[pipeline.agent_filter",),
    }

    if section not in owned_map:
        return None

    owned_prefixes = owned_map[section]
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


def _strip_section_lines(text: str, section: str) -> str:
    """Return the file text with all lines owned by ``section`` removed.

    Symmetric inverse of ``_extract_section_lines``: the union of both outputs
    reconstructs the original file (modulo trailing whitespace normalisation).
    Comment/blank lines that immediately precede an owned header are removed
    together with it, so they never accumulate on repeated saves.
    """
    owned_map: dict[str, tuple[str, ...]] = {
        "agent_types": ("[agent_types",),
        "keyboard.shortcuts": ("[[keyboard.shortcuts",),
        "audio.advanced": ("[audio.advanced",),
        "audio.sounds": ("[audio.sounds",),
        "stt.advanced": ("[stt.advanced",),
        "pipeline.submit_filter": ("[pipeline.submit_filter",),
        "pipeline.agent_filter": ("[pipeline.agent_filter",),
    }

    if section not in owned_map:
        return text

    owned_prefixes = owned_map[section]
    result: list[str] = []
    in_target = False
    comment_buf: list[str] = []  # pending comment/blank lines

    for line in text.splitlines(keepends=True):
        stripped = line.strip()

        if stripped.startswith("["):
            is_owned = any(stripped.startswith(p) for p in owned_prefixes)
            if is_owned:
                # Discard buffered comments — they belong to this owned header
                comment_buf = []
                in_target = True
            else:
                # Non-owned header: flush buffered comments, keep this line
                result.extend(comment_buf)
                comment_buf = []
                result.append(line)
                in_target = False

        elif in_target:
            pass  # skip owned content

        elif not stripped or stripped.startswith("#"):
            # Buffer — may precede an owned header
            comment_buf.append(line)

        else:
            # Regular non-owned content: flush buffer and keep
            result.extend(comment_buf)
            comment_buf = []
            result.append(line)

    # Flush any trailing comments/blanks that follow non-owned content
    result.extend(comment_buf)

    return "".join(result)


def _write_section_raw(section: str, user_content: str, config_path: Path) -> None:
    """Remove the section's owned keys from the config, then append the user's text."""
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
    else:
        text = ""
        config_path.parent.mkdir(parents=True, exist_ok=True)

    remaining = _strip_section_lines(text, section).rstrip("\n")
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

        raw = dict(doc.get("agent_types", {}))
        for _name, entry in raw.items():
            if _name == "default":
                if not isinstance(entry, str):
                    raise ValueError("agent_types.default must be a string")
            elif isinstance(entry, dict):
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

    elif section == "audio.advanced":
        from voxtype.config import AudioAdvancedConfig

        audio = doc.get("audio") or {}
        raw = audio.get("advanced") or {}
        AudioAdvancedConfig.model_validate(dict(raw))

    elif section == "stt.advanced":
        from voxtype.config import STTAdvancedConfig

        stt = doc.get("stt") or {}
        raw = stt.get("advanced") or {}
        STTAdvancedConfig.model_validate(dict(raw))

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
