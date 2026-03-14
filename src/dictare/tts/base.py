"""Base TTS interface and shared playback utilities."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import threading
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

# Module-level tracking of the current audio subprocess.
# Used by stop_audio_native() to interrupt playback from any thread/signal handler.
_audio_lock = threading.Lock()
_current_audio_proc: subprocess.Popen | None = None

def stop_audio_native() -> bool:
    """Kill the currently playing audio subprocess, if any.

    Returns:
        True if a process was found and terminated, False if nothing was playing.
    """
    global _current_audio_proc
    with _audio_lock:
        proc = _current_audio_proc
    if proc is None:
        return False
    try:
        proc.terminate()
    except (ProcessLookupError, OSError):
        pass
    return True

def play_audio_native(path: str | Path, *, timeout: float = 120.0, volume: float = 1.0) -> None:
    """Play an audio file using the native system player.

    Uses afplay on macOS, paplay/aplay on Linux.  All three read file
    headers (not extensions) so WAV, AIFF, and other formats work.

    Args:
        path: Path to audio file (WAV, AIFF, etc.).
        timeout: Maximum playback time in seconds.
        volume: Playback volume (0.0–1.0). Applied via player flags.
    """
    global _current_audio_proc
    path_str = str(path)

    if sys.platform == "darwin":
        cmd = ["afplay", "-v", str(volume), path_str]
    elif shutil.which("paplay"):
        # paplay volume: 0–65536 (100% = 65536)
        cmd = ["paplay", f"--volume={int(volume * 65536)}", path_str]
    elif shutil.which("aplay"):
        cmd = ["aplay", "-q", path_str]  # aplay has no volume flag
    else:
        logger.warning("No native audio player found (paplay/aplay)")
        return

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with _audio_lock:
        _current_audio_proc = proc
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait()
    finally:
        with _audio_lock:
            if _current_audio_proc is proc:
                _current_audio_proc = None

class TTSEngine(ABC):
    """Abstract text-to-speech interface."""

    @abstractmethod
    def speak(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
        volume: float = 1.0,
    ) -> bool:
        """Speak text aloud.

        Args:
            text: Text to speak.
            voice: Per-request voice override (engine-dependent, optional).
            language: Per-request language override (engine-dependent, optional).
            volume: Playback volume (0.0–1.0).

        Returns:
            True if successful.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if TTS engine is available."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get engine name."""
        pass

    def check_cache(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> Path | None:
        """Check if audio for *text* is already cached.

        Returns the WAV file path on cache hit, ``None`` on miss.
        Override in engines that support caching (e.g. Kokoro).
        """
        return None

    def list_voices(self) -> list[str]:
        """Return available voice names for this engine.

        Default: empty list (engine doesn't support voice listing).
        Override in subclasses that support it.
        """
        return []
