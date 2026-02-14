"""Audio feedback sounds for voxtype.

Provides bundled sound file paths and in-process audio playback.
Playback via sounddevice + soundfile (no external processes).
Bundled sounds are pre-loaded into memory at import time for zero-latency playback.

Thread safety: all sounddevice output calls are serialized through a single
worker thread via a queue.  PortAudio's global session is NOT thread-safe,
so concurrent sd.play() from multiple threads causes heap corruption.
The queue is for serialization only — sounds are fire-and-forget; one play
does NOT block the next unless an on_complete callback requires sd.wait().

Key function:
    play_audio(source, pause_mic, controller) - shared entry point for all playback.
    - pause_mic=False: fire-and-forget via queue.
    - pause_mic=True: registers play_id, transitions to PLAYING state (mic muted),
      plays audio, waits for completion, then sends PlayCompleteEvent to resume.
"""

from __future__ import annotations

import logging
import queue
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
DEFAULT_SOUND_START = _SOUNDS_DIR / "up-beep.wav"
DEFAULT_SOUND_STOP = _SOUNDS_DIR / "down-beep.wav"
DEFAULT_SOUND_TRANSCRIBING = _SOUNDS_DIR / "transcribing.wav"
DEFAULT_SOUND_READY = _SOUNDS_DIR / "ready.wav"


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


# ---------------------------------------------------------------------------
# Audio playback queue — serializes all sounddevice output on one thread
# ---------------------------------------------------------------------------

_play_queue: queue.Queue[tuple[str, Callable[[], None] | None] | None] = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()


def _ensure_worker() -> None:
    """Start the audio playback worker if not already running."""
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        t = threading.Thread(target=_audio_worker, daemon=True, name="voxtype-audio-out")
        t.start()
        _worker_started = True


def _audio_worker() -> None:
    """Single worker thread for all sounddevice output.

    Serializes sd.play()/sd.wait() calls to prevent concurrent access
    to PortAudio's global session (which is not thread-safe).

    Items are ``(path_str, on_complete | None)`` or ``None`` (shutdown).
    When *on_complete* is set the worker blocks with ``sd.wait()`` until
    playback finishes, then invokes the callback.  Otherwise it fires
    ``sd.play()`` and immediately processes the next item (fire-and-forget).
    """
    while True:
        item = _play_queue.get()
        if item is None:
            break

        path_str, on_complete = item
        try:
            cached = _sound_cache.get(path_str)
            if cached is not None:
                data, sr = cached
            else:
                import soundfile as sf

                data, sr = sf.read(path_str)
                _sound_cache[path_str] = (data, sr)

            import sounddevice as sd

            sd.play(data, sr)
            if on_complete:
                sd.wait()
        except Exception:
            logger.debug("Audio playback failed for %s", path_str, exc_info=True)
            _play_sound_file_fallback(path_str)
        finally:
            if on_complete:
                try:
                    on_complete()
                except Exception:
                    pass


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
        name: Filename (e.g., 'up-beep.wav', 'down-beep.wav')

    Returns:
        Path to the sound file.
    """
    return _SOUNDS_DIR / name


def play_sound_file(
    path: str | Path, *, on_complete: Callable[[], None] | None = None
) -> None:
    """Enqueue a sound file for playback on the audio worker thread.

    Non-blocking: returns immediately after enqueueing.
    Thread-safe: all sounddevice calls happen on a single worker thread.

    Args:
        path: Path to sound file (wav, etc.)
        on_complete: Optional callback invoked after playback finishes.
            When set, the worker blocks (sd.wait) until done, then calls it.
    """
    _ensure_worker()
    _play_queue.put((str(path), on_complete))


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
    """Play a sound file asynchronously (non-blocking, fire-and-forget).

    Alias for play_sound_file() — kept for backward compatibility.
    play_sound_file() is already non-blocking (queue-based).

    Args:
        path: Path to sound file (wav, etc.)
    """
    play_sound_file(path)


def play_audio(
    source: str | Path | Callable[[], None],
    *,
    pause_mic: bool = True,
    controller: Any = None,
) -> None:
    """Play audio, optionally pausing the microphone during playback.

    This is the shared entry point for all audio playback in voxtype.

    File paths are dispatched through the audio worker queue (thread-safe).
    Callable sources (e.g., TTS via subprocess) run on their own thread
    because they don't use sounddevice.

    Args:
        source: Path to audio file, or blocking callable that produces audio.
        pause_mic: If True and controller available, mute mic during playback
            via the PLAYING state transition. If False, fire-and-forget.
        controller: StateController instance. Required for pause_mic=True.
    """
    is_callable = callable(source)

    # --- Callable source (TTS) — runs on its own thread ---
    if is_callable:
        fn: Callable[[], None] = source  # type: ignore[assignment]

        if not pause_mic or controller is None:
            threading.Thread(target=fn, daemon=True).start()
            return

        from voxtype.core.state import AppState

        if controller.state == AppState.OFF:
            threading.Thread(target=fn, daemon=True).start()
            return

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
        return

    # --- File source — dispatched through the audio queue ---
    _path = source

    if not pause_mic or controller is None:
        play_sound_file(_path)
        return

    from voxtype.core.state import AppState

    if controller.state == AppState.OFF:
        play_sound_file(_path)
        return

    from voxtype.core.events import PlayCompleteEvent, PlayStartEvent

    try:
        play_id = controller.get_next_play_id()
        controller.send(PlayStartEvent(text="", source="audio"))
    except Exception:
        logger.debug("Failed to register play_id, playing without mic pause")
        play_sound_file(_path)
        return

    def on_complete() -> None:
        try:
            controller.send(
                PlayCompleteEvent(play_id=play_id, source="audio")
            )
        except Exception:
            pass

    play_sound_file(_path, on_complete=on_complete)


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
