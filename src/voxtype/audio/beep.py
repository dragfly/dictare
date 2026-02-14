"""Audio feedback sounds for voxtype.

Provides bundled sound file paths and in-process audio playback.
Playback via sounddevice + soundfile (no external processes).
Bundled sounds are pre-loaded into memory at import time for zero-latency playback.

Key function:
    play_audio(source, pause_mic, controller) - shared entry point for all playback.
    - pause_mic=False: fire-and-forget on background thread.
    - pause_mic=True: registers play_id, transitions to PLAYING state (mic muted),
      plays audio, then sends PlayCompleteEvent to resume listening.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_SOUNDS_DIR = Path(__file__).parent / "sounds"

# Default bundled sound files
DEFAULT_SOUND_START = _SOUNDS_DIR / "up-beep.mp3"
DEFAULT_SOUND_STOP = _SOUNDS_DIR / "down-beep.mp3"
DEFAULT_SOUND_TRANSCRIBING = _SOUNDS_DIR / "transcribing.mp3"
DEFAULT_SOUND_READY = _SOUNDS_DIR / "ready.mp3"

# Map event names to their default bundled sound files
_DEFAULT_SOUNDS: dict[str, Path] = {
    "start": DEFAULT_SOUND_START,
    "stop": DEFAULT_SOUND_STOP,
    "transcribing": DEFAULT_SOUND_TRANSCRIBING,
    "ready": DEFAULT_SOUND_READY,
    "sent": DEFAULT_SOUND_START,  # reuses up-beep
}

# Pre-loaded sound cache: path -> (numpy_array, sample_rate)
_sound_cache: dict[str, tuple[np.ndarray, int]] = {}

def _preload_sounds() -> None:
    """Pre-load bundled sounds into memory at import time."""
    try:
        import soundfile as sf
    except ImportError:
        logger.debug("soundfile not available, sounds will be loaded on demand")
        return

    for path in {DEFAULT_SOUND_START, DEFAULT_SOUND_STOP, DEFAULT_SOUND_TRANSCRIBING, DEFAULT_SOUND_READY}:
        try:
            data, sr = sf.read(path)
            _sound_cache[str(path)] = (data, sr)
        except Exception:
            logger.debug("Failed to preload %s", path)

_preload_sounds()

def get_sound_for_event(audio_config: Any, name: str) -> tuple[bool, str]:
    """Check if a sound event is enabled and return its file path.

    Considers the master switch (audio_feedback) and per-event config.
    For 'agent_announce', returns (enabled, "") since it uses TTS, not a file.

    Args:
        audio_config: AudioConfig instance.
        name: Event name (start, stop, transcribing, ready, sent, agent_announce).

    Returns:
        (enabled, path) — enabled=False means skip playback.
    """
    if not audio_config.audio_feedback:
        return False, ""

    sound_cfg = audio_config.sounds.get(name)
    if sound_cfg is None:
        # Unknown event or not configured — use default if available
        default = _DEFAULT_SOUNDS.get(name)
        return (True, str(default)) if default else (False, "")

    if not sound_cfg.enabled:
        return False, ""

    if name == "agent_announce":
        return True, ""  # TTS, no file path

    path = sound_cfg.path or str(_DEFAULT_SOUNDS.get(name, ""))
    return True, path

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

    Uses sounddevice for in-process playback. Falls back to system commands
    if sounddevice/soundfile are unavailable.

    Call this from a background thread. For non-blocking playback,
    use play_sound_file_async().

    Args:
        path: Path to sound file (mp3, wav, etc.)
    """
    path_str = str(path)
    try:
        # Check cache first (bundled sounds are pre-loaded)
        cached = _sound_cache.get(path_str)
        if cached is not None:
            import sounddevice as sd
            sd.play(cached[0], cached[1])
            sd.wait()
            return

        # Not cached — try loading and playing via sounddevice
        import sounddevice as sd
        import soundfile as sf
        data, sr = sf.read(path_str)
        # Cache for future use
        _sound_cache[path_str] = (data, sr)
        sd.play(data, sr)
        sd.wait()
    except Exception:
        # Fallback to system commands
        _play_sound_file_fallback(path_str)

def _play_sound_file_fallback(path_str: str) -> None:
    """Fallback: play via system commands when sounddevice is unavailable."""
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

def play_audio(
    source: str | Path | Callable[[], None],
    *,
    pause_mic: bool = True,
    controller: Any = None,
) -> None:
    """Play audio, optionally pausing the microphone during playback.

    This is the shared entry point for all audio playback in voxtype.
    Handles both file paths and arbitrary blocking callables (e.g., TTS).

    Args:
        source: Path to audio file, or blocking callable that produces audio.
        pause_mic: If True and controller available, mute mic during playback
            via the PLAYING state transition. If False, fire-and-forget.
        controller: StateController instance. Required for pause_mic=True.
    """
    # Determine the blocking play function
    fn: Callable[[], None]
    if callable(source):
        fn = source
    else:
        _path = source

        def fn() -> None:  # type: ignore[misc]
            play_sound_file(_path)

    # Fire-and-forget if no mic pausing needed
    if not pause_mic or controller is None:
        threading.Thread(target=fn, daemon=True).start()
        return

    # Check if mic is already off (no need to pause)
    from voxtype.core.state import AppState

    if controller.state == AppState.OFF:
        threading.Thread(target=fn, daemon=True).start()
        return

    # Pause mic: register play_id, transition to PLAYING, play, then complete
    from voxtype.core.events import PlayCompleteEvent, PlayStartEvent

    try:
        play_id = controller.get_next_play_id()
        controller.send(PlayStartEvent(text="", source="audio"))
    except Exception:
        logger.debug("Failed to register play_id, playing without mic pause")
        threading.Thread(target=fn, daemon=True).start()
        return

    def _play_with_events() -> None:
        try:
            fn()
        finally:
            try:
                controller.send(
                    PlayCompleteEvent(play_id=play_id, source="audio")
                )
            except Exception:
                pass

    threading.Thread(target=_play_with_events, daemon=True).start()

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
