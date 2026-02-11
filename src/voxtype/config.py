"""Configuration management for voxtype."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import tomllib
from pydantic import BaseModel, Field, ValidationError

# Environment variable prefix
ENV_PREFIX = "VOXTYPE_"


class ConfigError(Exception):
    """User-friendly configuration error."""

    pass


class SoundConfig(BaseModel):
    """Configuration for a single audio feedback event."""

    enabled: bool = Field(default=True, description="Enable this sound")
    path: str | None = Field(default=None, description="Custom sound file path (None = bundled default)")


def _default_sounds() -> dict[str, SoundConfig]:
    """Default sound configurations for all audio feedback events."""
    return {
        "start": SoundConfig(),
        "stop": SoundConfig(),
        "transcribing": SoundConfig(),
        "ready": SoundConfig(),
        "sent": SoundConfig(),
        "agent_announce": SoundConfig(),
    }


class AudioConfig(BaseModel):
    """Audio capture configuration."""

    sample_rate: int = Field(default=16000, description="Sample rate in Hz")
    channels: int = Field(default=1, description="Number of audio channels")
    device: str | None = Field(default=None, description="Audio device name (None = default)")
    max_duration: int = Field(default=60, description="Max recording duration in seconds")
    audio_feedback: bool = Field(
        default=True,
        description="Master switch: enable all audio feedback (individual sounds configured in [audio.sounds.*])",
    )
    silence_ms: int = Field(
        default=1200,
        description="VAD silence duration to end speech in milliseconds",
    )
    headphones_mode: bool = Field(
        default=False,
        description="Set to true when using headphones (TTS won't pause listening)",
    )
    pre_buffer_ms: int = Field(
        default=640,
        description="Audio pre-buffer in milliseconds (captures audio before VAD triggers)",
    )
    min_speech_ms: int = Field(
        default=150,
        description="Minimum speech duration in milliseconds before VAD triggers",
    )
    sounds: dict[str, SoundConfig] = Field(
        default_factory=_default_sounds,
        description="Per-event sound configuration (start, stop, transcribing, ready, sent, agent_announce)",
    )


class STTConfig(BaseModel):
    """Speech-to-text configuration."""

    model: str = Field(
        default="large-v3-turbo",
        description="Whisper model (tiny/base/small/medium/large-v3/large-v3-turbo)",
    )
    realtime_model: str = Field(
        default="tiny",
        description="Whisper model for realtime partial transcriptions (tiny recommended for low latency)",
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
    max_repetitions: int = Field(
        default=5,
        description="Max consecutive word repetitions before filtering (anti-hallucination)",
    )
    translate: bool = Field(
        default=False,
        description="Translate to English (Whisper task=translate). Any input language → English output.",
    )


def _default_hotkey() -> str:
    """Return platform-specific default hotkey."""
    import sys
    # macOS: Command key, Linux: Scroll Lock
    return "KEY_LEFTMETA" if sys.platform == "darwin" else "KEY_SCROLLLOCK"


class HotkeyConfig(BaseModel):
    """Hotkey configuration."""

    key: str = Field(
        default_factory=_default_hotkey,
        description="Toggle listening key (evdev key name). Default: Command on macOS, Scroll Lock on Linux",
    )
    device: str = Field(
        default="",
        description="Keyboard device name for hotkey (empty = auto-detect)",
    )


def _default_newline_keys() -> str:
    """Return platform-specific default for newline keys."""
    import sys
    return "shift+enter" if sys.platform == "darwin" else "alt+enter"


class OutputConfig(BaseModel):
    """Text output configuration."""

    mode: Literal["keyboard", "agents"] = Field(
        default="keyboard",
        description="Output mode: keyboard (type to focus) or agents (OpenVIP)",
    )
    typing_delay_ms: int = Field(
        default=5,
        description="Delay between characters in milliseconds",
    )
    auto_enter: bool = Field(
        default=False,
        description="Press Enter to submit after typing (False = visual newline only)",
    )
    submit_keys: str = Field(
        default="enter",
        description="Key combination for submit (when auto_enter=true)",
    )
    newline_keys: str = Field(
        default_factory=_default_newline_keys,
        description="Key combination for visual newline (when auto_enter=false). Default: alt+enter (Linux), shift+enter (macOS)",
    )


class KeyboardConfig(BaseModel):
    """Keyboard shortcuts configuration."""

    shortcuts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of keyboard shortcuts (configure via 'voxtype config shortcuts')",
    )


class ServerConfig(BaseModel):
    """OpenVIP HTTP/SSE server configuration.

    The server is always started in agent mode (--agents flag).
    Set enabled=true to also start it in keyboard mode (for StatusPanel monitoring).
    """

    enabled: bool = Field(
        default=False,
        description="Enable HTTP server in keyboard mode (always on in agent mode)",
    )
    host: str = Field(
        default="127.0.0.1",
        description="Host to bind server to (127.0.0.1 = localhost only for security)",
    )
    port: int = Field(
        default=8765,
        description="Port for OpenVIP HTTP server",
    )


class ClientConfig(BaseModel):
    """Agent client configuration for connecting to a remote engine."""

    url: str = Field(
        default="http://127.0.0.1:8765",
        description="Default engine URL for 'voxtype agent' command",
    )
    status_bar: bool = Field(
        default=True,
        description="Show persistent status bar in voxtype agent",
    )
    clear_on_start: bool = Field(
        default=True,
        description="Clear terminal before launching child process",
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    log_file: str = Field(
        default="",
        description="JSONL log file path for structured logging",
    )


class StatsConfig(BaseModel):
    """Session statistics configuration."""

    typing_wpm: int = Field(
        default=40,
        description="Average typing speed in words per minute (for time saved calculation)",
    )


class SubmitFilterConfig(BaseModel):
    """Submit filter configuration."""

    enabled: bool = Field(default=True, description="Enable submit trigger detection")
    triggers: dict[str, list[list[str]]] = Field(
        default_factory=lambda: {
            "it": [
                ["ok", "invia"],
                ["ok", "manda"],
                ["ok", "fatto"],
                ["va", "bene", "invia"],
                ["invia"],
                ["manda"],
                ["fatto"],
                ["adesso"],
            ],
            "en": [
                ["ok", "send"],
                ["ok", "submit"],
                ["go", "ahead"],
                ["submit"],
                ["send"],
                ["go"],
            ],
            "es": [
                ["ok", "enviar"],
                ["enviar"],
                ["envía"],
                ["listo"],
            ],
            "de": [
                ["ok", "senden"],
                ["senden"],
                ["abschicken"],
                ["fertig"],
            ],
            "fr": [
                ["ok", "envoyer"],
                ["envoyer"],
                ["envoie"],
                ["terminé"],
            ],
        },
        description="Trigger patterns by language code (checked: message language + English)",
    )
    confidence_threshold: float = Field(
        default=0.85,
        description="Minimum confidence to trigger submit (0.0-1.0)",
    )
    max_scan_words: int = Field(
        default=15,
        description="Maximum words from end to scan for triggers",
    )
    decay_rate: float = Field(
        default=0.95,
        description="Confidence decay rate per word from end (0.95 = 5% per word)",
    )


class AgentFilterConfig(BaseModel):
    """Agent switch filter configuration."""

    enabled: bool = Field(
        default=False,
        description="Enable voice-controlled agent switching (say 'agent <name>')",
    )
    triggers: list[str] = Field(
        default_factory=lambda: ["agent"],
        description="Trigger words that precede agent name (add your language: 'agente', 'agent', etc.)",
    )
    match_threshold: float = Field(
        default=0.5,
        description="Minimum fuzzy match score for agent name (0.0-1.0)",
    )


class PipelineConfig(BaseModel):
    """Pipeline filter configuration."""

    enabled: bool = Field(default=True, description="Enable the message pipeline")
    submit_filter: SubmitFilterConfig = Field(
        default_factory=SubmitFilterConfig,
        description="Submit trigger detection filter",
    )
    agent_filter: AgentFilterConfig = Field(
        default_factory=AgentFilterConfig,
        description="Voice-controlled agent switching filter",
    )


class DaemonConfig(BaseModel):
    """Daemon configuration."""

    socket_path: str = Field(
        default="",
        description="Path to daemon Unix socket (empty = use platform default)",
    )

    def get_socket_path(self) -> str:
        """Get actual socket path, using platform default if not specified."""
        if self.socket_path:
            return self.socket_path
        from voxtype.utils.platform import get_socket_dir

        return str(get_socket_dir() / "daemon.sock")
    preload_tts: bool = Field(
        default=True,
        description="Preload TTS engine on daemon start",
    )
    preload_stt: bool = Field(
        default=False,
        description="Preload STT engine on daemon start",
    )
    idle_timeout: int = Field(
        default=0,
        description="Shutdown daemon after N seconds of inactivity (0 = never)",
    )


class TTSConfig(BaseModel):
    """Text-to-speech configuration."""

    engine: Literal["espeak", "say", "piper", "coqui", "qwen3", "outetts"] = Field(
        default="espeak",
        description="TTS engine: espeak, say (macOS), piper, coqui, outetts (MLX)",
    )
    language: str = Field(
        default="en",
        description="Language code (en, es, de, it, fr, etc.)",
    )
    speed: int = Field(
        default=175,
        description="Speech speed in WPM (espeak: 80-500, say: 90-720, others: ignored)",
    )
    voice: str = Field(
        default="",
        description="Voice name or speaker WAV path (engine-specific)",
    )


class Config(BaseModel):
    """Main configuration."""

    audio: AudioConfig = Field(default_factory=AudioConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    keyboard: KeyboardConfig = Field(default_factory=KeyboardConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    client: ClientConfig = Field(default_factory=ClientConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    stats: StatsConfig = Field(default_factory=StatsConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)

    editor: str = Field(
        default="",
        description="Editor command for 'voxtype config edit' (empty = $EDITOR or system default)",
    )
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

    Example: stt.model -> VOXTYPE_STT_MODEL
    """
    return ENV_PREFIX + key.upper().replace(".", "_")


def _parse_value(value: str, current_type: type) -> Any:
    """Parse string value to appropriate type."""
    if current_type is bool:
        return value.lower() in ("true", "1", "yes", "on")
    elif current_type is int:
        return int(value)
    elif current_type is float:
        return float(value)
    else:
        return value


def _apply_env_overrides(config: Config) -> Config:
    """Apply environment variable overrides to config.

    Environment variables follow the pattern: VOXTYPE_SECTION_KEY
    Example: VOXTYPE_STT_MODEL=large-v3
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
        try:
            config = Config.model_validate(data)
        except ValidationError as e:
            errors = []
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                msg = err["msg"]
                val = err.get("input", "")
                errors.append(f"  • {loc}: {msg} (got: {val!r})")
            raise ConfigError(
                f"Invalid configuration in {config_path}:\n" + "\n".join(errors)
            ) from None
    else:
        config = Config()

    # Apply environment variable overrides
    return _apply_env_overrides(config)


def get_config_value(key: str, config: Config | None = None) -> Any:
    """Get a config value by dot-notation key.

    Args:
        key: Dot-notation key like 'stt.model' or 'verbose'
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
        key: Dot-notation key like 'stt.model' or 'verbose'
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

            # Handle nested dicts as subsections
            for key, value in values.items():
                if isinstance(value, dict):
                    # Check if values are themselves dicts (three-level nesting)
                    if value and all(isinstance(v, dict) for v in value.values()):
                        for subkey, subvalue in value.items():
                            lines.append(f"[{section}.{key}.{subkey}]\n")
                            for k, v in subvalue.items():
                                lines.append(f"{k} = {_format_toml_value(v)}\n")
                            lines.append("\n")
                    else:
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
    elif isinstance(value, list):
        if not value:
            return "[]"
        # Check if it's a list of dicts (inline tables)
        if isinstance(value[0], dict):
            items = []
            for item in value:
                pairs = ", ".join(f'{k} = {_format_toml_value(v)}' for k, v in item.items())
                items.append(f"{{ {pairs} }}")
            return "[\n    " + ",\n    ".join(items) + ",\n]"
        else:
            # Simple list
            return "[" + ", ".join(_format_toml_value(v) for v in value) + "]"
    elif isinstance(value, dict):
        pairs = ", ".join(f'{k} = {_format_toml_value(v)}' for k, v in value.items())
        return f"{{ {pairs} }}"
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
        if field_name in ("audio", "stt", "tts", "hotkey", "output", "keyboard", "server", "logging", "stats", "daemon", "pipeline"):
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
        ("tts", TTSConfig),
        ("hotkey", HotkeyConfig),
        ("output", OutputConfig),
        ("keyboard", KeyboardConfig),
        ("server", ServerConfig),
        ("logging", LoggingConfig),
        ("stats", StatsConfig),
        ("daemon", DaemonConfig),
        ("pipeline", PipelineConfig),
    ]

    for section_name, section_class in sections:
        section_config = section_class()
        for field_name, field_info in section_class.model_fields.items():  # type: ignore[attr-defined]
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
    import sys

    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / "config.toml"

    # Platform-specific defaults
    hotkey = "KEY_LEFTMETA" if sys.platform == "darwin" else "KEY_SCROLLLOCK"
    hotkey_comment = "Command key" if sys.platform == "darwin" else "Scroll Lock"
    newline_keys = "shift+enter" if sys.platform == "darwin" else "alt+enter"

    default_config = f"""\
# voxtype configuration
#
# All values shown are defaults. Uncomment and change as needed.

[audio]
sample_rate = 16000
channels = 1
# device = "default"            # Audio device name (None = system default)
audio_feedback = true            # Master switch for all audio feedback
silence_ms = 1200                # VAD silence duration to end speech (ms)
# headphones_mode = false        # Set to true when using headphones (TTS won't pause listening)
# max_duration = 60              # Max recording duration in seconds

# Advanced VAD tuning
# pre_buffer_ms = 640            # Audio captured before VAD triggers (increase if speech start is clipped)
# min_speech_ms = 150            # Min speech duration before VAD activates (lower = faster, may trigger on noise)

# Per-event sound configuration (disable individual sounds or set custom paths)
# [audio.sounds.start]           # OFF → LISTENING beep
# enabled = true
# path = "/path/to/custom-start.mp3"
#
# [audio.sounds.stop]            # → OFF beep
# enabled = true
#
# [audio.sounds.transcribing]    # LISTENING → TRANSCRIBING
# enabled = true
#
# [audio.sounds.ready]           # TRANSCRIBING → LISTENING
# enabled = true
#
# [audio.sounds.sent]            # File write / max duration beep
# enabled = true
#
# [audio.sounds.agent_announce]  # TTS agent name on switch
# enabled = true

[stt]
model = "large-v3-turbo"         # tiny, base, small, medium, large-v3, large-v3-turbo
language = "auto"                # auto-detect, or "en", "de", "fr", etc.
device = "auto"                  # auto, cpu, cuda
compute_type = "int8"
beam_size = 5
hw_accel = true                  # Enable hardware acceleration
max_repetitions = 5              # Anti-hallucination: max consecutive word repeats
# hotwords = "voxtype,joshua"    # Boost recognition of specific words
# translate = false              # Translate any language to English

[hotkey]
key = "{hotkey}"  # {hotkey_comment} (toggle listening)

[output]
mode = "keyboard"                # keyboard or agents
typing_delay_ms = 5
auto_enter = false               # Visual newline only
# submit_keys = "enter"          # Keys for submit (when auto_enter=true)
# newline_keys = "{newline_keys}"  # Keys for visual newline (when auto_enter=false)

# Keyboard shortcuts - configure interactively with: voxtype config shortcuts
# Example:
# [[keyboard.shortcuts]]
# keys = "Ctrl+Alt+N"
# command = "project-next"

[server]
# host = "127.0.0.1"             # Bind address (use "0.0.0.0" for remote agents)
# port = 8765                     # OpenVIP HTTP server port

[client]
# url = "http://127.0.0.1:8765"  # Default engine URL for 'voxtype agent'
# status_bar = true               # Show persistent status bar in voxtype agent
# clear_on_start = true            # Clear terminal before launching child process

[logging]
log_file = ""

[stats]
typing_wpm = 40                  # Your average typing speed (for time saved calculation)

# Editor for 'voxtype config edit'. If empty, uses $EDITOR or system default.
# Examples:
#   editor = "vim"
#   editor = "nano"
#   editor = "code --wait"          # VS Code (--wait keeps terminal until closed)
#   editor = "subl --wait"          # Sublime Text
#   editor = "open -a TextEdit"     # macOS TextEdit

verbose = false
"""

    with open(config_path, "w") as f:
        f.write(default_config)

    return config_path
