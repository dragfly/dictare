"""Shared CLI helpers."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

console = Console(
    force_terminal=None,  # Auto-detect
    force_interactive=None,  # Auto-detect
    legacy_windows=False,  # Use modern terminal codes
    safe_box=True,  # Use safe box drawing chars for compatibility
)


def auto_detect_acceleration(config, cpu_only: bool = False) -> None:
    """Auto-detect hardware acceleration (MLX on macOS, CUDA on Linux)."""
    from voxtype.utils.hardware import auto_detect_acceleration

    auto_detect_acceleration(config, cpu_only=cpu_only, console=console)


def apply_cli_overrides(
    config,
    *,
    model: str | None,
    hotkey: str | None,
    language: str | None,
    auto_enter: bool,
    max_duration: int | None,
    verbose: bool | None,
    typing_delay: int | None,
    silence_ms: int | None,
    log_file: str | None,
    no_audio_feedback: bool,
    no_hw_accel: bool,
    translate: bool = False,
) -> None:
    """Apply CLI options to config.

    Boolean flags use negative form (--no-X) for features that are ON by default.
    """
    if model:
        config.stt.model = model
    if hotkey:
        config.hotkey.key = hotkey
    if language:
        config.stt.language = language
    if auto_enter:
        config.output.auto_enter = True
    if max_duration:
        config.audio.max_duration = max_duration
    if verbose is not None:
        config.verbose = verbose
    if typing_delay is not None:
        config.output.typing_delay_ms = typing_delay
    if silence_ms is not None:
        config.audio.silence_ms = silence_ms
    if log_file:
        config.logging.log_file = log_file
    if no_audio_feedback:
        config.audio.audio_feedback = False
    if no_hw_accel:
        config.stt.hw_accel = False
    if translate:
        config.stt.translate = True


def create_logger(config, agents: list[str] | None = None):
    """Create JSONL logger for session.

    Logging is always enabled by default to ~/.local/share/voxtype/logs/.
    - INFO level (default): metadata only (chars, duration) - no text content
    - DEBUG level (--verbose): includes actual text content

    Args:
        config: Application configuration.
        agents: Optional list of agent IDs (affects log file name).

    Returns:
        JSONLLogger instance.
    """
    from voxtype import __version__
    from voxtype.logging.jsonl import JSONLLogger, LogLevel, get_default_log_path

    # Determine log level from verbose flag
    level = LogLevel.DEBUG if config.verbose else LogLevel.INFO

    # Determine log file path
    if config.logging.log_file:
        # User specified a custom log file
        log_path = Path(config.logging.log_file)
    else:
        # Use default path based on mode
        if agents:
            # Multi-agent: use first agent name
            log_path = get_default_log_path(f"agent.{agents[0]}")
        else:
            log_path = get_default_log_path("listen")

    log_params = {
        "input_mode": "vad",  # PTT mode removed in v2.2.0
        "log_level": level.name,
        "silence_ms": config.audio.silence_ms,
        "stt_model": config.stt.model,
        "stt_language": config.stt.language,
        "output_mode": config.output.mode,
    }
    if agents:
        log_params["agents"] = agents

    return JSONLLogger(log_path, __version__, level=level, params=log_params)
