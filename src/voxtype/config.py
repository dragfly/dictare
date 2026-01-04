"""Configuration management for voxtype."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

# Environment variable prefix
ENV_PREFIX = "VOXTYPE_"


class AudioConfig(BaseModel):
    """Audio capture configuration."""

    sample_rate: int = Field(default=16000, description="Sample rate in Hz")
    channels: int = Field(default=1, description="Number of audio channels")
    device: str | None = Field(default=None, description="Audio device name (None = default)")
    max_duration: int = Field(default=60, description="Max recording duration in seconds")
    audio_feedback: bool = Field(
        default=True,
        description="Play beep when entering/exiting LISTENING mode",
    )
    silence_ms: int = Field(
        default=1200,
        description="VAD silence duration to end speech in milliseconds",
    )


class STTConfig(BaseModel):
    """Speech-to-text configuration."""

    model_size: str = Field(
        default="large-v3-turbo",
        description="Whisper model size (tiny/base/small/medium/large-v3/large-v3-turbo)",
    )
    language: str = Field(
        default="auto",
        description="Language code or 'auto' for auto-detection",
    )
    compute_type: str = Field(
        default="int8",
        description="Compute type for faster-whisper (int8/float16/float32)",
    )
    device: str = Field(
        default="auto",
        description="Device to use (auto/cpu/cuda) - auto detects best available",
    )
    beam_size: int = Field(default=5, description="Beam size for decoding")
    hw_accel: bool = Field(
        default=True,
        description="Enable hardware acceleration (CUDA on Linux, MLX on macOS)",
    )
    hotwords: str = Field(
        default="",
        description="Comma-separated words to boost recognition (e.g., 'voxtype,joshua')",
    )


class HotkeyConfig(BaseModel):
    """Hotkey configuration."""

    key: str = Field(
        default="KEY_SCROLLLOCK",
        description="Toggle listening key (evdev key name)",
    )
    device: str = Field(
        default="",
        description="Keyboard device name for hotkey (empty = auto-detect)",
    )


class OutputConfig(BaseModel):
    """Text output configuration."""

    method: Literal["keyboard", "agent"] = Field(
        default="keyboard",
        description="Output method: keyboard (type) or agent (file for inputmux)",
    )
    typing_delay_ms: int = Field(
        default=5,
        description="Delay between characters in milliseconds",
    )
    auto_enter: bool = Field(
        default=False,
        description="Press Enter to submit after typing (False = visual newline only)",
    )


class CommandConfig(BaseModel):
    """Voice command configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable voice command processing",
    )
    wake_word: str = Field(
        default="",
        description="Wake word to activate (e.g., 'Joshua')",
    )
    mode: Literal["transcription", "command"] = Field(
        default="transcription",
        description="Processing mode: transcription (fast) or command (LLM)",
    )
    ollama_model: str = Field(
        default="qwen2.5:1.5b",
        description="Ollama model for intent classification",
    )
    ollama_timeout: float = Field(
        default=5.0,
        description="Ollama request timeout in seconds",
    )


class KeyboardConfig(BaseModel):
    """Keyboard shortcuts configuration."""

    shortcuts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of keyboard shortcuts with keys, command, and optional args",
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    log_file: str = Field(
        default="",
        description="JSONL log file path for structured logging",
    )


class Config(BaseModel):
    """Main configuration."""

    audio: AudioConfig = Field(default_factory=AudioConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    command: CommandConfig = Field(default_factory=CommandConfig)
    keyboard: KeyboardConfig = Field(default_factory=KeyboardConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    verbose: bool = Field(default=False, description="Enable verbose output")


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    config_dir = Path.home() / ".config" / "voxtype"
    return config_dir


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.toml"


def _key_to_env_var(key: str) -> str:
    """Convert config key to environment variable name.

    Example: stt.model_size -> VOXTYPE_STT_MODEL_SIZE
    """
    return ENV_PREFIX + key.upper().replace(".", "_")


def _parse_value(value: str, current_type: type) -> Any:
    """Parse string value to appropriate type."""
    if current_type == bool:
        return value.lower() in ("true", "1", "yes", "on")
    elif current_type == int:
        return int(value)
    elif current_type == float:
        return float(value)
    else:
        return value


def _apply_env_overrides(config: Config) -> Config:
    """Apply environment variable overrides to config.

    Environment variables follow the pattern: VOXTYPE_SECTION_KEY
    Example: VOXTYPE_STT_MODEL_SIZE=large-v3
    """
    config_dict = config.model_dump()

    for section_name, section in config_dict.items():
        if isinstance(section, dict):
            for key, value in section.items():
                env_var = _key_to_env_var(f"{section_name}.{key}")
                env_value = os.environ.get(env_var)
                if env_value is not None:
                    section[key] = _parse_value(env_value, type(value) if value is not None else str)
        else:
            # Top-level keys like 'verbose'
            env_var = _key_to_env_var(section_name)
            env_value = os.environ.get(env_var)
            if env_value is not None:
                config_dict[section_name] = _parse_value(env_value, type(section) if section is not None else str)

    return Config.model_validate(config_dict)


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from file with environment variable overrides.

    Priority (highest to lowest):
    1. Environment variables (VOXTYPE_*)
    2. Config file (~/.config/voxtype/config.toml)
    3. Built-in defaults

    Args:
        config_path: Path to config file. If None, uses default location.

    Returns:
        Loaded configuration with defaults and overrides applied.
    """
    if config_path is None:
        config_path = get_config_path()

    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        config = Config.model_validate(data)
    else:
        config = Config()

    # Apply environment variable overrides
    return _apply_env_overrides(config)


def get_config_value(key: str, config: Config | None = None) -> Any:
    """Get a config value by dot-notation key.

    Args:
        key: Dot-notation key like 'stt.model_size' or 'verbose'
        config: Config object (loads default if None)

    Returns:
        The config value

    Raises:
        KeyError: If key not found
    """
    if config is None:
        config = load_config()

    parts = key.split(".")
    obj: Any = config

    for part in parts:
        if hasattr(obj, part):
            obj = getattr(obj, part)
        else:
            raise KeyError(f"Unknown config key: {key}")

    return obj


def set_config_value(key: str, value: str, config_path: Path | None = None) -> None:
    """Set a config value by dot-notation key.

    Args:
        key: Dot-notation key like 'stt.model_size' or 'verbose'
        value: String value (will be converted to appropriate type)
        config_path: Path to config file (uses default if None)

    Raises:
        KeyError: If key not found
    """
    if config_path is None:
        config_path = get_config_path()

    # Load current config
    config = load_config(config_path)
    config_dict = config.model_dump()

    parts = key.split(".")

    if len(parts) == 1:
        # Top-level key
        if parts[0] not in config_dict:
            raise KeyError(f"Unknown config key: {key}")
        current_value = config_dict[parts[0]]
        config_dict[parts[0]] = _parse_value(value, type(current_value) if current_value is not None else str)
    elif len(parts) == 2:
        section, field = parts
        if section not in config_dict or not isinstance(config_dict[section], dict):
            raise KeyError(f"Unknown config section: {section}")
        if field not in config_dict[section]:
            raise KeyError(f"Unknown config key: {key}")
        current_value = config_dict[section][field]
        config_dict[section][field] = _parse_value(value, type(current_value) if current_value is not None else str)
    else:
        raise KeyError(f"Invalid config key format: {key}")

    # Validate the new config
    Config.model_validate(config_dict)

    # Write back to TOML
    _write_config(config_dict, config_path)


def _write_config(config_dict: dict, config_path: Path) -> None:
    """Write config dict to TOML file."""
    config_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# voxtype configuration\n"]

    # Top-level keys first
    for key, value in config_dict.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {_format_toml_value(value)}\n")

    lines.append("\n")

    # Sections
    for section, values in config_dict.items():
        if isinstance(values, dict):
            lines.append(f"[{section}]\n")
            for key, value in values.items():
                if isinstance(value, dict):
                    # Skip nested dicts here, handle them as subsections
                    pass
                else:
                    lines.append(f"{key} = {_format_toml_value(value)}\n")
            lines.append("\n")

            # Handle nested dicts as subsections (e.g., controller.keys)
            for key, value in values.items():
                if isinstance(value, dict):
                    lines.append(f"[{section}.{key}]\n")
                    for subkey, subvalue in value.items():
                        lines.append(f"{subkey} = {_format_toml_value(subvalue)}\n")
                    lines.append("\n")

    with open(config_path, "w") as f:
        f.writelines(lines)


def _format_toml_value(value: Any) -> str:
    """Format a value for TOML output."""
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, str):
        return f'"{value}"'
    elif value is None:
        return '""'  # TOML doesn't have null, use empty string
    else:
        return str(value)


def list_config_keys() -> list[tuple[str, str, Any, str, str]]:
    """List all config keys with their descriptions and defaults.

    Returns:
        List of (key, type, default, description, env_var) tuples
    """
    result = []
    config = Config()

    # Top-level fields
    for field_name, field_info in Config.model_fields.items():
        if field_name in ("audio", "stt", "hotkey", "output", "command", "controller", "logging"):
            # These are sections, handle below
            continue
        value = getattr(config, field_name)
        env_var = _key_to_env_var(field_name)
        result.append((
            field_name,
            type(value).__name__,
            value,
            field_info.description or "",
            env_var,
        ))

    # Sections
    sections = [
        ("audio", AudioConfig),
        ("stt", STTConfig),
        ("hotkey", HotkeyConfig),
        ("output", OutputConfig),
        ("command", CommandConfig),
        ("keyboard", KeyboardConfig),
        ("logging", LoggingConfig),
    ]

    for section_name, section_class in sections:
        section_config = section_class()
        for field_name, field_info in section_class.model_fields.items():
            key = f"{section_name}.{field_name}"
            value = getattr(section_config, field_name)
            env_var = _key_to_env_var(key)
            result.append((
                key,
                type(value).__name__ if value is not None else "str",
                value,
                field_info.description or "",
                env_var,
            ))

    return result


def create_default_config() -> Path:
    """Create default configuration file.

    Returns:
        Path to the created config file.
    """
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / "config.toml"

    default_config = """\
# voxtype configuration

[audio]
sample_rate = 16000
channels = 1
# device = "default"  # Uncomment to specify audio device
audio_feedback = true  # Play beep on listening mode toggle
silence_ms = 1200      # VAD silence threshold in ms

[stt]
model_size = "large-v3-turbo"  # tiny, base, small, medium, large-v3, large-v3-turbo
language = "auto"              # auto-detect, or "en", "de", "fr", etc.
device = "auto"                # auto, cpu, cuda
compute_type = "int8"
beam_size = 5
hw_accel = true                # Enable hardware acceleration
# hotwords = "voxtype,joshua"  # Boost recognition of specific words

[hotkey]
key = "KEY_SCROLLLOCK"  # evdev key name (toggle listening)

[output]
method = "keyboard"    # keyboard or agent
typing_delay_ms = 5
auto_enter = false     # Visual newline only

[command]
enabled = true
wake_word = ""         # e.g., "hey joshua"
mode = "transcription" # transcription or command
ollama_model = "qwen2.5:1.5b"
ollama_timeout = 5.0

# Keyboard shortcuts (require modifiers like Ctrl, Alt, Cmd)
# [[keyboard.shortcuts]]
# keys = "Ctrl+Shift+L"
# command = "toggle-listening"
#
# [[keyboard.shortcuts]]
# keys = "Ctrl+Alt+1"
# command = "switch-to-project"
# [keyboard.shortcuts.args]
# name = "macina"

[logging]
log_file = ""

verbose = false
"""

    with open(config_path, "w") as f:
        f.write(default_config)

    return config_path
