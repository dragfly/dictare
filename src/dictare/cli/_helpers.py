"""Shared CLI helpers."""

from __future__ import annotations

from rich.console import Console

console = Console(
    force_terminal=None,  # Auto-detect
    force_interactive=None,  # Auto-detect
    legacy_windows=False,  # Use modern terminal codes
    safe_box=True,  # Use safe box drawing chars for compatibility
)

def auto_detect_acceleration(config, cpu_only: bool = False) -> None:
    """Auto-detect hardware acceleration (MLX on macOS, CUDA on Linux)."""
    from dictare.utils.hardware import auto_detect_acceleration

    auto_detect_acceleration(config, cpu_only=cpu_only, console=console)
