"""Configuration management for dictare."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Environment variable prefix
ENV_PREFIX = "DICTARE_"

class ConfigError(Exception):
    """User-friendly configuration error."""

    pass

class SoundConfig(BaseModel):
    """Configuration for a single audio feedback event."""

    enabled: bool = Field(default=True, description="Enable this sound")
    path: str | None = Field(default=None, description="Custom sound file path (None = bundled default)")
    volume: float = Field(default=1.0, ge=0.0, le=1.0, description="Playback volume (0.0–1.0)")
    focus_gated: bool = Field(
        default=False,
        description="Skip this sound when the active agent's terminal has focus",
    )

def _default_sounds() -> dict[str, SoundConfig]:
    """Default sound configurations for all audio feedback events."""
    return {
        "start": SoundConfig(),
        "stop": SoundConfig(),
        "transcribing": SoundConfig(enabled=False, volume=0.15),
        "ready": SoundConfig(),
        "transcribed": SoundConfig(volume=1.0, focus_gated=True),
        "submit": SoundConfig(volume=0.25, focus_gated=True),
        "sent": SoundConfig(volume=0.25),
        "agent_announce": SoundConfig(),
    }

class AudioAdvancedConfig(BaseModel):
    """Low-level audio tuning parameters (rarely need changing)."""

    sample_rate: int = Field(default=16000, description="Sample rate in Hz")
    channels: int = Field(default=1, description="Number of audio channels")
    device: str | None = Field(default=None, description="Audio device name (None = default)")
    pre_buffer_ms: int = Field(
        default=640,
        description="Audio pre-buffer in milliseconds (captures audio before VAD triggers)",
    )
    min_speech_ms: int = Field(
        default=150,
        description="Minimum speech duration in milliseconds before VAD triggers",
    )
    transcribing_sound_min_ms: int = Field(
        default=8000,
        description="Minimum audio duration (ms) before the transcribing sound plays. Short clips skip it.",
    )

class AudioConfig(BaseModel):
    """Audio capture configuration."""

    input_device: str = Field(
        default="",
        description="Input device name (empty = system default)",
    )
    output_device: str = Field(
        default="",
        description="Output device name (empty = system default)",
    )
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
    advanced: AudioAdvancedConfig = Field(
        default_factory=AudioAdvancedConfig,
        description="Low-level audio tuning (sample rate, channels, device, buffers)",
    )
    sounds: dict[str, SoundConfig] = Field(
        default_factory=_default_sounds,
        description="Per-event sound configuration (start, stop, transcribing, ready, transcribed, submit, sent, agent_announce)",
    )

    @model_validator(mode="before")
    @classmethod
    def _merge_sound_defaults(cls, values: Any) -> Any:
        """Merge user sound configs over application defaults.

        Without this, a partial ``[audio.sounds.transcribed]`` section in
        TOML would replace the entire default SoundConfig, losing fields
        like ``focus_gated=True`` that differ from Pydantic field defaults.
        """
        if not isinstance(values, dict):
            return values

        # Migrate audio.advanced.device → audio.input_device
        advanced = values.get("advanced")
        if isinstance(advanced, dict) and advanced.get("device") and not values.get("input_device"):
            values["input_device"] = advanced["device"]
            advanced["device"] = None

        # Merge user sounds over defaults
        user_sounds = values.get("sounds")
        if isinstance(user_sounds, dict):
            defaults = _default_sounds()
            merged: dict[str, Any] = {}
            for key, default_cfg in defaults.items():
                if key in user_sounds:
                    user_val = user_sounds[key]
                    if isinstance(user_val, dict):
                        # Merge: default fields + user overrides
                        merged[key] = {**default_cfg.model_dump(), **user_val}
                    else:
                        merged[key] = user_val
                else:
                    merged[key] = default_cfg
            # Preserve any extra user-defined sound events
            for key in user_sounds:
                if key not in merged:
                    merged[key] = user_sounds[key]
            values["sounds"] = merged

        return values

class STTAdvancedConfig(BaseModel):
    """Low-level STT tuning parameters (rarely need changing)."""

    device: Literal["auto", "cpu", "cuda", "mlx"] = Field(
        default="auto",
        description="Device to use — auto detects best available (cuda, mlx, or cpu)",
    )
    compute_type: Literal["int8", "float16", "float32"] = Field(
        default="int8",
        description="Compute precision for faster-whisper (int8 = fastest, float32 = most accurate)",
    )
    beam_size: int = Field(
        default=5,
        description="Beam width for decoding (higher = slower but more accurate)",
    )
    hotwords: str = Field(
        default="",
        description="Comma-separated words to boost recognition (e.g., 'dictare,joshua')",
    )
    max_repetitions: int = Field(
        default=5,
        description="Max consecutive word repetitions before filtering (anti-hallucination)",
    )

class STTConfig(BaseModel):
    """Speech-to-text configuration."""

    model: str = Field(
        default="parakeet-v3",
        description="STT model: parakeet-v3 (default), large-v3-turbo, or large-v3",
    )
    language: str = Field(
        default="auto",
        description="Language code or 'auto' for auto-detection",
    )
    translate: bool = Field(
        default=False,
        description="Translate to English (Whisper task=translate). Any input language → English output.",
    )
    hw_accel: bool = Field(
        default=True,
        description="Enable hardware acceleration (CUDA on Linux, MLX on macOS)",
    )
    advanced: STTAdvancedConfig = Field(
        default_factory=STTAdvancedConfig,
        description="Low-level STT tuning (device, compute type, beam size, hotwords)",
    )

def _default_hotkey() -> str:
    """Return platform-specific default hotkey."""
    import sys
    # macOS: Right Command key, Linux: Scroll Lock
    return "KEY_RIGHTMETA" if sys.platform == "darwin" else "KEY_SCROLLLOCK"

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
    mode_switch_modifier: str = Field(
        default="",
        description="Modifier key that, when held while tapping the hotkey, switches between agent and keyboard mode (e.g. KEY_RIGHTALT). Empty = disabled.",
    )

def _default_newline_keys() -> str:
    """Return platform-specific default for newline keys."""
    import sys
    return "shift+enter" if sys.platform == "darwin" else "alt+enter"

class OutputConfig(BaseModel):
    """Text output configuration."""

    mode: Literal["agents", "keyboard"] = Field(
        default="agents",
        description="Output mode: agents (OpenVIP SSE, default) or keyboard (type into focused window)",
    )
    typing_delay_ms: int = Field(
        default=2,
        description="Keyboard mode only: delay between characters in milliseconds",
    )
    auto_submit: bool = Field(
        default=False,
        description="Automatically submit each transcription (press Enter / send to agent). When off, text accumulates until manual submit via double-tap or trigger word.",
    )
    submit_keys: str = Field(
        default="enter",
        description="Keyboard mode only: key combination to submit (when auto_submit=true)",
    )
    newline_keys: str = Field(
        default_factory=_default_newline_keys,
        description="Keyboard mode only: key for visual newline (when auto_submit=false). Default: alt+enter (Linux), shift+enter (macOS)",
    )

class KeyboardConfig(BaseModel):
    """Keyboard shortcuts configuration."""

    shortcuts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of keyboard shortcuts (configure via 'dictare config shortcuts')",
    )

class ServerConfig(BaseModel):
    """OpenVIP HTTP/SSE server configuration."""

    host: str = Field(
        default="127.0.0.1",
        description="Host to bind server to (127.0.0.1 = localhost only for security)",
    )
    port: int = Field(
        default=8770,
        description="Port for OpenVIP HTTP server",
    )

class ClientConfig(BaseModel):
    """Agent client configuration for connecting to a remote engine."""

    url: str = Field(
        default="http://127.0.0.1:8770/openvip",
        description="Default engine OpenVIP URL for 'dictare agent' command",
    )
    status_bar: bool = Field(
        default=True,
        description="Show persistent status bar in dictare agent",
    )
    clear_on_start: bool = Field(
        default=True,
        description="Clear terminal before launching child process",
    )
    claim_key: str = Field(
        default="ctrl+\\",
        description="Hotkey to claim this PTY as active voice target (e.g. ctrl+\\, ctrl+])",
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
        default_factory=dict,
        description="Trigger patterns by language code. Empty by default — configure in config.toml.",
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
        default=True,
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

class AgentTypeConfig(BaseModel):
    """Agent type configuration (defines a named agent preset and its launch command)."""

    command: list[str] = Field(
        description="Command and arguments to launch the agent",
    )
    description: str = Field(
        default="",
        description="Human-readable description of this agent type",
    )
    continue_args: list[str] = Field(
        default_factory=list,
        description="Args inserted after argv[0] when --continue is passed (e.g. [\"-c\"] for Claude Code, [\"--resume\"] for Codex)",
    )
    live_dangerously_args: list[str] = Field(
        default_factory=list,
        description="Args inserted after argv[0] when --live-dangerously is passed (e.g. [\"--dangerously-skip-permissions\"] for Claude Code)",
    )

class AgentTypesConfig(BaseModel):
    """Container for agent type presets.

    ``default`` names the preset used when running ``dictare agent`` without
    ``--type``.  All other keys are named presets (``AgentTypeConfig``).

    TOML structure::

        [agent_types]
        default = "claude"

        [agent_types.claude]
        command = ["claude"]
        continue_args = ["-c"]
    """

    model_config = ConfigDict(extra="allow")

    default: str | None = Field(
        default=None,
        description="Default agent type used when running 'dictare agent' without --type",
    )

    def get(self, name: str) -> AgentTypeConfig | None:
        """Return the named preset, or None if not found."""
        extras = self.model_extra or {}
        if name not in extras:
            return None
        return AgentTypeConfig.model_validate(extras[name])

    def entries(self) -> dict[str, AgentTypeConfig]:
        """Return all named presets as a validated dict."""
        result = {}
        for k, v in (self.model_extra or {}).items():
            if isinstance(v, (dict, AgentTypeConfig)):
                try:
                    result[k] = AgentTypeConfig.model_validate(v)
                except Exception:
                    pass
        return result

    def items(self):  # type: ignore[override]
        return self.entries().items()

    def __contains__(self, name: object) -> bool:
        return name in (self.model_extra or {})

    def __bool__(self) -> bool:
        return bool(self.model_extra)

def _default_mute_triggers() -> dict[str, list[list[str]]]:
    return {"*": [["ok|okay", "mute|stop"]]}

def _default_listen_triggers() -> dict[str, list[list[str]]]:
    return {"*": [["ok|okay", "listen"]]}

class MuteFilterConfig(BaseModel):
    """Voice mute filter configuration.

    Trigger patterns and TTS feedback for the mute/listen feature.
    The filter detects triggers; the engine executes mute/unmute and
    plays TTS feedback using the phrases configured here.
    """

    enabled: bool = Field(default=True, description="Enable voice mute/unmute filter")
    mute_triggers: dict[str, list[list[str]]] = Field(
        default_factory=_default_mute_triggers,
        description="Trigger patterns to mute voice (by language). Use '*' for language-agnostic.",
    )
    listen_triggers: dict[str, list[list[str]]] = Field(
        default_factory=_default_listen_triggers,
        description="Trigger patterns to unmute voice (by language). Use '*' for language-agnostic.",
    )
    mute_phrases: list[str] = Field(
        default_factory=lambda: [
            "Going quiet.",
            "I'll be here when you need me.",
            "Taking a break.",
            "Standing by.",
        ],
        description="TTS phrases spoken when muting (random selection)",
    )
    listen_phrases: list[str] = Field(
        default_factory=lambda: [
            "I'm all ears.",
            "Ready when you are.",
            "Listening.",
            "At your service.",
        ],
        description="TTS phrases spoken when unmuting (random selection)",
    )
    confidence_threshold: float = Field(
        default=0.85,
        description="Minimum confidence to trigger mute/unmute (0.0-1.0)",
    )
    max_scan_words: int = Field(
        default=10,
        description="Maximum words from end to scan for triggers",
    )
    decay_rate: float = Field(
        default=0.95,
        description="Confidence decay rate per word from end (0.95 = 5% per word)",
    )

class PipelineConfig(BaseModel):
    """Pipeline filter configuration."""

    enabled: bool = Field(default=True, description="Enable the message pipeline")
    mute_filter: MuteFilterConfig = Field(
        default_factory=MuteFilterConfig,
        description="Voice mute/unmute filter (OK mute / OK listen)",
    )
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
        from dictare.utils.platform import get_socket_dir

        return str(get_socket_dir() / "daemon.sock")

    restore_listening: bool = Field(
        default=False,
        description="Restore listening state on restart (false = always start off)",
    )

class TTSConfig(BaseModel):
    """Text-to-speech configuration."""

    engine: Literal["espeak", "say", "piper", "outetts", "kokoro"] = Field(
        default="say" if sys.platform == "darwin" else "piper",
        description="TTS engine: espeak, say (macOS only), piper, outetts (MLX, Apple Silicon), kokoro (ONNX)",
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
    agent_types: AgentTypesConfig = Field(
        default_factory=AgentTypesConfig,
        description='Agent type presets. Set default = "claude" for default type. Names with dots must be quoted: [agent_types."sonnet-4.6"].',
    )

    editor: str = Field(
        default="",
        description="Editor command for 'dictare config edit' (empty = $EDITOR or system default)",
    )
    verbose: bool = Field(default=False, description="Enable verbose output")

def get_config_dir() -> Path:
    """Get the configuration directory path."""
    config_dir = Path.home() / ".config" / "dictare"
    return config_dir

def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.toml"

def _key_to_env_var(key: str) -> str:
    """Convert config key to environment variable name.

    Example: stt.model -> DICTARE_STT_MODEL
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

    Environment variables follow the pattern: DICTARE_SECTION_KEY
    Example: DICTARE_STT_MODEL=large-v3
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

def load_raw_values(config_path: Path | None = None) -> dict[str, Any]:
    """Load raw TOML values as a flat dotted-key dict.

    Only returns keys explicitly set in the config file — no Pydantic defaults.
    Nested sections are flattened: ``{stt: {language: "it"}}`` → ``{"stt.language": "it"}``.
    """
    if config_path is None:
        config_path = get_config_path()
    if not config_path.exists():
        return {}
    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    flat: dict[str, Any] = {}

    def _flatten(obj: dict, prefix: str = "") -> None:
        for k, v in obj.items():
            full = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
            if isinstance(v, dict):
                _flatten(v, full)
            else:
                flat[full] = v

    _flatten(data)
    return flat

def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from file with environment variable overrides.

    Priority (highest to lowest):
    1. Environment variables (DICTARE_*)
    2. Config file (~/.config/dictare/config.toml)
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

def _stamp_version(doc: Any) -> None:
    """Stamp the config document with the current dictare version.

    Writes ``_version = "dictare/X.Y.Z"`` at the top level.
    Used for future config migration — if a breaking config change is made,
    the migration tool can read this to know what version wrote the file.
    """
    from dictare import __version__

    doc["_version"] = f"dictare/{__version__}"

def set_config_value(key: str, value: str, config_path: Path | None = None) -> None:
    """Set a config value by dot-notation key.

    Uses tomlkit to preserve comments and formatting.

    Args:
        key: Dot-notation key like 'stt.model' or 'verbose'
        value: String value (will be converted to appropriate type)
        config_path: Path to config file (uses default if None)

    Raises:
        KeyError: If key not found
    """
    import tomlkit

    if config_path is None:
        config_path = get_config_path()

    # Validate the key exists in the schema
    config = load_config(config_path)
    config_dict = config.model_dump()

    parts = key.split(".")

    if len(parts) == 1:
        if parts[0] not in config_dict:
            raise KeyError(f"Unknown config key: {key}")
        current_value = config_dict[parts[0]]
    elif len(parts) == 2:
        section, field = parts
        if section not in config_dict or not isinstance(config_dict[section], dict):
            raise KeyError(f"Unknown config section: {section}")
        if field not in config_dict[section]:
            raise KeyError(f"Unknown config key: {key}")
        current_value = config_dict[section][field]
    else:
        raise KeyError(f"Invalid config key format: {key}")

    parsed = _parse_value(value, type(current_value) if current_value is not None else str)

    # Validate the new value
    test_dict = config_dict.copy()
    if len(parts) == 1:
        test_dict[parts[0]] = parsed
    else:
        test_dict[parts[0]] = {**test_dict[parts[0]], parts[1]: parsed}
    Config.model_validate(test_dict)

    # Read file with tomlkit (preserves comments and formatting)
    if config_path.exists():
        doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    else:
        doc = tomlkit.document()

    # Set the value
    if len(parts) == 1:
        doc[parts[0]] = parsed
    else:
        section, field = parts
        if section not in doc:
            doc.add(section, tomlkit.table())
        doc[section][field] = parsed  # type: ignore[index]

    # Stamp version for future config migration
    _stamp_version(doc)

    # Write back (preserves all comments and formatting)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(tomlkit.dumps(doc), encoding="utf-8")

def delete_config_value(key: str, config_path: Path | None = None) -> None:
    """Remove a config key from the TOML file, reverting to the Pydantic default.

    Args:
        key: Dot-notation key like 'stt.model' or 'verbose'
        config_path: Path to config file (uses default if None)

    Raises:
        KeyError: If key is not a valid schema key
    """
    import tomlkit

    if config_path is None:
        config_path = get_config_path()

    # Validate the key exists in the schema
    config = load_config(config_path)
    config_dict = config.model_dump()

    parts = key.split(".")
    if len(parts) == 1:
        if parts[0] not in config_dict:
            raise KeyError(f"Unknown config key: {key}")
    elif len(parts) == 2:
        section, field = parts
        if section not in config_dict or not isinstance(config_dict[section], dict):
            raise KeyError(f"Unknown config section: {section}")
        if field not in config_dict[section]:
            raise KeyError(f"Unknown config key: {key}")
    else:
        raise KeyError(f"Invalid config key format: {key}")

    if not config_path.exists():
        return  # Nothing to delete

    doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    if len(parts) == 1:
        if parts[0] in doc:
            del doc[parts[0]]
    else:
        section, field = parts
        tbl = doc.get(section)
        if isinstance(tbl, dict) and field in tbl:
            del tbl[field]

    _stamp_version(doc)
    config_path.write_text(tomlkit.dumps(doc), encoding="utf-8")

def list_config_keys() -> list[tuple[str, str, Any, str, str]]:
    """List all config keys with their descriptions and defaults.

    Returns:
        List of (key, type, default, description, env_var) tuples
    """
    result = []
    config = Config()

    # Derive sections from Config fields: any field whose type is a BaseModel subclass
    # (except agent_types which is dynamic)
    _skip_sections = {"agent_types"}
    sections: list[tuple[str, type]] = []
    for field_name, field_info in Config.model_fields.items():
        field_type = field_info.annotation
        if field_type is not None and isinstance(field_type, type) and issubclass(field_type, BaseModel) and field_name not in _skip_sections:
            sections.append((field_name, field_type))

    section_names = {name for name, _ in sections}

    # Top-level fields (skip sections)
    for field_name, field_info in Config.model_fields.items():
        if field_name in section_names or field_name in _skip_sections:
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
    for section_name, section_class in sections:
        section_config = section_class()
        for field_name, field_info in section_class.model_fields.items():  # type: ignore[attr-defined]
            key = f"{section_name}.{field_name}"
            value = getattr(section_config, field_name)
            env_var = _key_to_env_var(key)
            # Nested BaseModel sub-fields are exposed as "dict" so the UI
            # renders them as TOML editors (e.g. audio.advanced).
            if isinstance(value, BaseModel):
                type_name = "dict"
            else:
                type_name = type(value).__name__ if value is not None else "str"
            result.append((
                key,
                type_name,
                value,
                field_info.description or "",
                env_var,
            ))

    # agent_types has dynamic entries — expose as a single "dict" field
    # so the UI renders it as a TOML editor
    agent_types_field = Config.model_fields["agent_types"]
    result.append((
        "agent_types",
        "dict",
        {},
        agent_types_field.description or "Agent type presets",
        _key_to_env_var("agent_types"),
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
    hotkey = "KEY_RIGHTMETA" if sys.platform == "darwin" else "KEY_SCROLLLOCK"
    hotkey_comment = "Right Command key" if sys.platform == "darwin" else "Scroll Lock"
    newline_keys = "shift+enter" if sys.platform == "darwin" else "alt+enter"

    default_config = f"""\
# dictare configuration
#
# Only non-default values need to be uncommented.
# Uncomment and change any line to override the default.
# Docs: dictare config list

# editor = ""                     # Editor for 'dictare config edit' ($EDITOR if empty)
# verbose = false

[audio]
# input_device = ""               # Input device name (empty = system default)
# output_device = ""              # Output device name (empty = system default)
# max_duration = 60               # Max recording duration (seconds)
# audio_feedback = true           # Master switch for all audio feedback
# silence_ms = 1200               # VAD silence to end speech (ms)
# headphones_mode = false         # TTS won't pause listening when true

# [audio.advanced]                # Low-level tuning — edit via Settings > Advanced Audio
# sample_rate = 16000             # Sample rate in Hz (Whisper requires 16000)
# channels = 1                    # Number of audio channels
# device = ""                     # Audio device name (empty = system default)
# pre_buffer_ms = 640             # Audio captured before VAD triggers (ms)
# min_speech_ms = 150             # Min speech duration before VAD activates (ms)
# transcribing_sound_min_ms = 8000  # Min audio length (ms) to trigger typewriter sound

# [audio.sounds.*]                # Per-event sounds — edit via Settings > Sounds
# [audio.sounds.start]            # OFF → LISTENING  (up-beep.wav)
# enabled = true
# path = ""                       # Empty = bundled default
# volume = 1.0                    # 0.0–1.0
# focus_gated = false             # Skip when agent terminal has focus
# [audio.sounds.stop]             # LISTENING → OFF  (down-beep.wav)
# enabled = true
# [audio.sounds.transcribing]     # LISTENING → TRANSCRIBING  (typewriter.wav, looped)
# enabled = false                  # Disabled by default
# volume = 0.15                   # Subtle background typewriter during STT processing
# focus_gated = false             # Plays regardless of terminal focus
# [audio.sounds.ready]            # TRANSCRIBING → LISTENING  (carriage return)
# enabled = true
# volume = 1.0
# [audio.sounds.transcribed]      # Transcription received  (random pencil-write clip)
# enabled = true
# volume = 1.0
# focus_gated = true              # Skipped when agent terminal has focus
# [audio.sounds.submit]           # Submit action: typewriter burst  (typewriter-burst.wav)
# enabled = true
# volume = 0.25
# focus_gated = true              # Skipped when agent terminal has focus
# [audio.sounds.sent]             # Standalone carriage-return  (carriage-return.wav)
# enabled = true
# volume = 0.25
# [audio.sounds.agent_announce]   # TTS announces agent name on switch
# enabled = true

[stt]
# model = "large-v3-turbo"        # Default: Whisper large-v3-turbo (fast + accurate, MLX on Mac)
#                                 # Also: parakeet-v3, tiny, base, small, medium, large-v3
# language = "auto"               # Auto-detect, or "en", "it", "de", "fr", etc.
# translate = false               # Any language → English
# hw_accel = true                 # CUDA on Linux, MLX on macOS

# [stt.advanced]                  # Low-level tuning — edit via Settings > Advanced STT
# device = "auto"                 # auto, cpu, cuda, mlx
# compute_type = "int8"           # int8 (fastest), float16, float32 (most accurate)
# beam_size = 5                   # Higher = slower but more accurate
# hotwords = ""                   # Boost recognition: "dictare,joshua" (turbo model only)
# max_repetitions = 5             # Anti-hallucination: max consecutive repeats

[tts]
# engine = "say"                 # say (macOS, default), piper (Linux, default), espeak, outetts (MLX)
# language = "en"
# speed = 175                     # WPM (espeak: 80-500, say: 90-720)
# voice = ""                      # Voice name or speaker WAV path

[hotkey]
# key = "{hotkey}"                # {hotkey_comment} (toggle listening)
# device = ""                     # Keyboard device (empty = auto-detect)

[output]
# mode = "agents"                 # agents (default, OpenVIP SSE) or keyboard (type into focused window)
# typing_delay_ms = 2             # keyboard mode only: delay between characters (ms)
# auto_submit = false              # auto-send each transcription (default: accumulate)
# submit_keys = "enter"           # keyboard mode only
# newline_keys = "{newline_keys}" # keyboard mode only

# [keyboard]
# shortcuts = []                  # Configure via: dictare config shortcuts

[server]
# host = "127.0.0.1"
# port = 8770

[client]
# url = "http://127.0.0.1:8770/openvip"
# status_bar = true
# clear_on_start = true
# claim_key = "ctrl+\\\\"           # Hotkey to claim this agent (ctrl+\\, ctrl+], etc.)

# [logging]
# log_file = ""                   # JSONL structured log path

# [stats]
# typing_wpm = 40                 # Your typing speed (for time saved calc)

# [daemon]
# socket_path = ""

[pipeline]
# enabled = true

[pipeline.mute_filter]
# enabled = true
# confidence_threshold = 0.85
# max_scan_words = 10
# decay_rate = 0.95

# TTS phrases spoken on mute/unmute (random selection)
# mute_phrases = ["Going quiet.", "I'll be here when you need me.", "Taking a break.", "Standing by."]
# listen_phrases = ["I'm all ears.", "Ready when you are.", "Listening.", "At your service."]

# Mute triggers — say these to mute voice input (engine keeps running, text discarded)
# [pipeline.mute_filter.mute_triggers]
# "*" = [["ok|okay", "mute|stop"]]
# es = [["ok|okay", "silencio|para"]]
# de = [["ok|okay", "stumm|stopp"]]

# Listen triggers — say these to unmute and resume normal voice input
# [pipeline.mute_filter.listen_triggers]
# "*" = [["ok|okay", "listen"]]
# es = [["ok|okay", "escucha"]]
# de = [["ok|okay", "hoer|zuhoeren"]]

[pipeline.submit_filter]
# enabled = true
# confidence_threshold = 0.85
# max_scan_words = 15
# decay_rate = 0.95               # 5% confidence decay per word from end

# Submit triggers by language.
# Each trigger is a multi-word sequence — all words must appear in order.
# Single words trigger too easily; always use 2+ word sequences.
# Use "|" for alternatives within a slot: "ok|okay" matches either word.
# Punctuation is ignored: "ok, send." matches "ok send".
# Use "*" for language-agnostic triggers (always active regardless of detected language).
[pipeline.submit_filter.triggers]
"*" = [
    ["ok|okay", "send|submit"],
]
# es = [
#     ["ok|okay", "enviar|mandar"],
# ]
# de = [
#     ["ok|okay", "senden|abschicken"],
# ]
# fr = [
#     ["ok|okay", "envoyer|soumettre"],
# ]
# it = [
#     ["ok|okay", "invia|manda"],
# ]

[pipeline.agent_filter]
# enabled = false
# triggers = ["agent"]
# match_threshold = 0.5

[agent_types]
default = "sonnet"

[agent_types.sonnet]
command = ["claude", "--model", "claude-sonnet-4-6", "--max-turns", "1000"]
continue_args = ["-c"]
live_dangerously_args = ["--dangerously-skip-permissions"]
description = "Claude Sonnet 4.6"

[agent_types.opus]
command = ["claude", "--model", "claude-opus-4-6", "--max-turns", "1000"]
continue_args = ["-c"]
live_dangerously_args = ["--dangerously-skip-permissions"]
description = "Claude Opus 4.6"

[agent_types.chatgpt]
command = ["codex"]
continue_args = ["resume", "--last"]
live_dangerously_args = ["--dangerously-bypass-approvals-and-sandbox"]
description = "OpenAI Codex"
"""

    with open(config_path, "w") as f:
        f.write(default_config)

    return config_path
