"""Configuration management for voxtype."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

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

class STTConfig(BaseModel):
    """Speech-to-text configuration."""

    backend: Literal["faster-whisper", "openai"] = Field(
        default="faster-whisper",
        description="STT backend to use",
    )
    model_size: str = Field(
        default="base",
        description="Whisper model size (tiny/base/small/medium/large-v3)",
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
        default="cpu",
        description="Device to use (cpu/cuda)",
    )
    beam_size: int = Field(default=5, description="Beam size for decoding")

class HotkeyConfig(BaseModel):
    """Hotkey configuration."""

    backend: Literal["evdev", "pynput", "auto"] = Field(
        default="auto",
        description="Hotkey backend to use",
    )
    key: str = Field(
        default="KEY_SCROLLLOCK",
        description="Push-to-talk key (evdev key name)",
    )

class InjectionConfig(BaseModel):
    """Text injection configuration."""

    backend: Literal["ydotool", "wtype", "clipboard", "auto"] = Field(
        default="auto",
        description="Text injection backend to use",
    )
    typing_delay_ms: int = Field(
        default=0,
        description="Delay between characters in milliseconds",
    )
    fallback_to_clipboard: bool = Field(
        default=True,
        description="Fall back to clipboard if typing fails",
    )
    auto_enter: bool = Field(
        default=False,
        description="Automatically press Enter after typing text",
    )
    auto_paste: bool = Field(
        default=True,
        description="Auto Ctrl+V after clipboard copy (when using clipboard mode)",
    )

class CloudConfig(BaseModel):
    """Cloud STT configuration."""

    openai_api_key: str = Field(default="", description="OpenAI API key for Whisper API")

class CommandConfig(BaseModel):
    """Voice command configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable voice command processing",
    )
    classifier_backend: Literal["auto", "ollama", "keyword"] = Field(
        default="auto",
        description="Intent classifier backend (auto tries ollama first)",
    )
    ollama_model: str = Field(
        default="llama3.2:1b",
        description="Ollama model for intent classification",
    )
    ollama_timeout: float = Field(
        default=5.0,
        description="Ollama request timeout in seconds",
    )
    format_text: bool = Field(
        default=True,
        description="Use LLM to format/clean transcribed text",
    )

class Config(BaseModel):
    """Main configuration."""

    audio: AudioConfig = Field(default_factory=AudioConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    injection: InjectionConfig = Field(default_factory=InjectionConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    command: CommandConfig = Field(default_factory=CommandConfig)

    # UI settings
    show_notification: bool = Field(default=True, description="Show desktop notifications")
    verbose: bool = Field(default=False, description="Enable verbose output")

def get_config_dir() -> Path:
    """Get the configuration directory path."""
    config_dir = Path.home() / ".config" / "voxtype"
    return config_dir

def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.toml"

def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from file.

    Args:
        config_path: Path to config file. If None, uses default location.

    Returns:
        Loaded configuration with defaults applied.
    """
    if config_path is None:
        config_path = get_config_path()

    if not config_path.exists():
        return Config()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    return Config.model_validate(data)

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

[stt]
backend = "faster-whisper"
model_size = "base"  # tiny, base, small, medium, large-v3
language = "auto"    # auto-detect, or "en", "it", etc.
compute_type = "int8"
beam_size = 5

[hotkey]
backend = "auto"
key = "KEY_SCROLLLOCK"  # evdev key name

[injection]
backend = "auto"  # ydotool, wtype, clipboard
typing_delay_ms = 0
fallback_to_clipboard = true
auto_enter = false  # Press Enter after typing

[cloud]
# openai_api_key = ""  # For cloud STT (optional)

[command]
enabled = true
classifier_backend = "auto"  # auto, ollama, keyword
ollama_model = "llama3.2:1b"
ollama_timeout = 5.0
format_text = true

# UI settings
show_notification = true
verbose = false
"""

    with open(config_path, "w") as f:
        f.write(default_config)

    return config_path
