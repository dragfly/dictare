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

# Error/busy beep: five loud high beeps (very noticeable, annoying)
_BEEP_BUSY = np.concatenate([
    _generate_beep(900, 0.12),  # Beep 1
    np.zeros(int(_SAMPLE_RATE * 0.06), dtype=np.float32),
    _generate_beep(900, 0.12),  # Beep 2
    np.zeros(int(_SAMPLE_RATE * 0.06), dtype=np.float32),
    _generate_beep(900, 0.12),  # Beep 3
    np.zeros(int(_SAMPLE_RATE * 0.06), dtype=np.float32),
    _generate_beep(900, 0.12),  # Beep 4
    np.zeros(int(_SAMPLE_RATE * 0.06), dtype=np.float32),
    _generate_beep(900, 0.12),  # Beep 5
])

def warmup_audio() -> None:
    """Pre-initialize audio output to avoid delay on first beep."""
    try:
        import sounddevice as sd
        sd.play(np.zeros(100, dtype=np.float32), _SAMPLE_RATE, blocking=True)
    except Exception:
        pass

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

# TTS mode announcements per language
_MODE_PHRASES = {
    "it": {"transcription": "modalità trascrizione", "command": "modalità comando"},
    "en": {"transcription": "transcription mode", "command": "command mode"},
    "es": {"transcription": "modo transcripción", "command": "modo comando"},
    "fr": {"transcription": "mode transcription", "command": "mode commande"},
    "de": {"transcription": "Transkriptionsmodus", "command": "Befehlsmodus"},
    "pt": {"transcription": "modo transcrição", "command": "modo comando"},
}

# macOS voice names per language
_MACOS_VOICES = {
    "it": "Alice",
    "en": "Samantha",
    "es": "Monica",
    "fr": "Thomas",
    "de": "Anna",
    "pt": "Luciana",
}

def speak_mode(mode: str, language: str = "en") -> None:
    """Speak the current mode using OS TTS.

    Args:
        mode: Either "transcription" or "command"
        language: Language code (it, en, es, fr, de, pt)
    """
    import subprocess
    import sys
    import threading

    # Get phrase for language, fallback to English
    phrases = _MODE_PHRASES.get(language, _MODE_PHRASES["en"])
    text = phrases.get(mode, mode)

    def _speak():
        try:
            if sys.platform == "darwin":
                # macOS: use 'say' command
                voice = _MACOS_VOICES.get(language, "Samantha")
                subprocess.run(
                    ["say", "-v", voice, text],
                    capture_output=True,
                    timeout=5,
                )
            else:
                # Linux: try espeak-ng, then espeak, then spd-say
                lang_code = language if language != "en" else "en-us"
                for cmd in [
                    ["espeak-ng", "-v", lang_code, text],
                    ["espeak", "-v", lang_code, text],
                    ["spd-say", "-l", language, text],
                ]:
                    try:
                        subprocess.run(cmd, capture_output=True, timeout=5)
                        break
                    except FileNotFoundError:
                        continue
        except Exception:
            pass  # Silently fail if TTS not available

    # Run in background thread to not block
    threading.Thread(target=_speak, daemon=True).start()
