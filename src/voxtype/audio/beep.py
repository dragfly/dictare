"""Audio feedback sounds for voxtype.

Start/stop beeps use bundled WAV files played via OS audio player
(afplay on macOS, aplay/paplay on Linux) to avoid sounddevice conflicts.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

_SOUNDS_DIR = Path(__file__).parent / "sounds"

def _play_wav(filename: str) -> None:
    """Play a WAV file from the sounds directory (non-blocking)."""
    path = _SOUNDS_DIR / filename
    if not path.exists():
        return

    def _play() -> None:
        try:
            if sys.platform == "darwin":
                subprocess.run(["afplay", str(path)], capture_output=True, timeout=5)
            else:
                for cmd in [["paplay", str(path)], ["aplay", "-q", str(path)]]:
                    try:
                        subprocess.run(cmd, capture_output=True, timeout=5)
                        break
                    except FileNotFoundError:
                        continue
        except Exception:
            pass

    threading.Thread(target=_play, daemon=True).start()

def warmup_audio() -> None:
    """No-op, kept for API compatibility."""

def play_beep_start() -> None:
    """Play beep indicating listening mode started."""
    _play_wav("up-beep.mp3")

def play_beep_stop() -> None:
    """Play beep indicating listening mode stopped."""
    _play_wav("down-beep.mp3")

def play_beep_sent() -> None:
    """Play beep indicating transcription was sent/written."""
    _play_wav("up-beep.mp3")  # Reuse start beep until dedicated sound is added

def play_beep_busy() -> None:
    """Play beep indicating system is busy (speech ignored)."""
    _play_wav("down-beep.mp3")  # Reuse stop beep until dedicated sound is added

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
