"""Simple audio feedback (beeps) for user notifications."""

from __future__ import annotations

import numpy as np

# Pre-generate beep at module load for instant playback
_BEEP_DURATION = 0.15  # seconds
_BEEP_FREQ = 800  # Hz
_SAMPLE_RATE = 16000


def _generate_beep(
    frequency: float = _BEEP_FREQ,
    duration: float = _BEEP_DURATION,
    sample_rate: int = _SAMPLE_RATE,
) -> np.ndarray:
    """Generate a simple sine wave beep."""
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    # Apply envelope to avoid clicks
    envelope = np.ones_like(t)
    fade_samples = int(sample_rate * 0.01)  # 10ms fade
    envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
    envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
    return np.sin(2 * np.pi * frequency * t) * envelope * 0.3


# Pre-generated beeps
_BEEP_START = _generate_beep(800, 0.15)  # Higher pitch for start
_BEEP_STOP = _generate_beep(400, 0.15)  # Lower pitch for stop

# Error/busy beep: two short beeps
_BEEP_BUSY = np.concatenate([
    _generate_beep(600, 0.08),  # First short beep
    np.zeros(int(_SAMPLE_RATE * 0.05), dtype=np.float32),  # Gap
    _generate_beep(600, 0.08),  # Second short beep
])


def play_beep_start() -> None:
    """Play a beep indicating listening mode started."""
    try:
        import sounddevice as sd

        sd.play(_BEEP_START, _SAMPLE_RATE, blocking=False)
    except Exception:
        pass  # Don't fail on audio errors


def play_beep_stop() -> None:
    """Play a beep indicating listening mode stopped."""
    try:
        import sounddevice as sd

        sd.play(_BEEP_STOP, _SAMPLE_RATE, blocking=False)
    except Exception:
        pass  # Don't fail on audio errors


def play_beep_busy() -> None:
    """Play a beep indicating system is busy (speech ignored)."""
    try:
        import sounddevice as sd

        sd.play(_BEEP_BUSY, _SAMPLE_RATE, blocking=False)
    except Exception:
        pass  # Don't fail on audio errors
