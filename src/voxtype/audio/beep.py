"""Audio feedback sounds for voxtype.

Provides bundled sound file paths and OS-level audio playback.
Playback via afplay (macOS) / paplay/aplay (Linux) to avoid sounddevice conflicts.

State management (PLAYING transition, mic muting) is handled by the caller
(core/app.py or app/controller.py) using the shared TTS ID counter system.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

_SOUNDS_DIR = Path(__file__).parent / "sounds"

# Default bundled sound files
DEFAULT_SOUND_START = _SOUNDS_DIR / "up-beep.mp3"
DEFAULT_SOUND_STOP = _SOUNDS_DIR / "down-beep.mp3"


def get_sound_path(name: str) -> Path:
    """Get path to a bundled sound file.

    Args:
        name: Filename (e.g., 'up-beep.mp3', 'down-beep.mp3')

    Returns:
        Path to the sound file.
    """
    return _SOUNDS_DIR / name


def play_sound_file(path: str | Path) -> None:
    """Play a sound file (blocking).

    Call this from a background thread. For non-blocking playback,
    use play_sound_file_async().

    Args:
        path: Path to sound file (mp3, wav, etc.)
    """
    path_str = str(path)
    try:
        if sys.platform == "darwin":
            subprocess.run(["afplay", path_str], capture_output=True, timeout=5)
        else:
            for cmd in [["paplay", path_str], ["aplay", "-q", path_str]]:
                try:
                    subprocess.run(cmd, capture_output=True, timeout=5)
                    break
                except FileNotFoundError:
                    continue
    except Exception:
        pass


def play_sound_file_async(path: str | Path) -> None:
    """Play a sound file in a background thread (non-blocking, no mic muting).

    Use this for simple fire-and-forget playback when mic muting is not needed
    (e.g., when mic is already off).

    Args:
        path: Path to sound file (mp3, wav, etc.)
    """
    threading.Thread(target=play_sound_file, args=(path,), daemon=True).start()


def warmup_audio() -> None:
    """No-op, kept for API compatibility."""


# Legacy API - kept for backward compatibility
def play_beep_start() -> None:
    """Play beep indicating listening mode started."""
    play_sound_file_async(DEFAULT_SOUND_START)


def play_beep_stop() -> None:
    """Play beep indicating listening mode stopped."""
    play_sound_file_async(DEFAULT_SOUND_STOP)


def play_beep_sent() -> None:
    """Play beep indicating transcription was sent/written."""
    play_sound_file_async(DEFAULT_SOUND_START)


def play_beep_busy() -> None:
    """Play beep indicating system is busy (speech ignored)."""
    play_sound_file_async(DEFAULT_SOUND_STOP)


# TTS mode announcements per language (fallback to English for unsupported languages)
_MODE_PHRASES = {
    "it": {"transcription": "modalità trascrizione", "command": "modalità comandi"},
    "en": {"transcription": "transcription mode", "command": "command mode"},
}

# macOS voice names per language
_MACOS_VOICES = {
    "it": "Alice",
    "en": "Samantha",
}


def speak_mode(mode: str, language: str = "en") -> None:
    """Speak the current mode using OS TTS.

    Args:
        mode: Either "transcription" or "command"
        language: Language code (it, en, es, fr, de, pt)
    """
    # Get phrase for language, fallback to English
    phrases = _MODE_PHRASES.get(language, _MODE_PHRASES["en"])
    text = phrases.get(mode, mode)

    def _speak() -> None:
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
