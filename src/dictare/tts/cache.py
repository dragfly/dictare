"""TTS audio cache — deterministic audio file caching with LRU eviction.

Cache key = sha256(engine|text|language|voice) → {hash}.audio
Hit = instant playback from cache. Miss = generate + save + play.
LRU via filesystem mtime (touch on use, evict oldest).
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".local" / "share" / "dictare" / "tts-cache"
_MAX_CACHED = 1000


def cache_key(engine: str, text: str, language: str, voice: str) -> str:
    """Compute deterministic cache key from TTS parameters."""
    raw = f"{engine}|{text}|{language}|{voice}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_path(key: str) -> Path:
    """Return the audio file path for a cache key."""
    return _CACHE_DIR / f"{key}.audio"


def cache_hit(key: str) -> Path | None:
    """Check if cached audio exists. If yes, touch mtime and return path."""
    path = cache_path(key)
    if path.exists():
        # Touch mtime → LRU tracking
        os.utime(path)
        return path
    return None


def cache_save(key: str, audio_path: Path) -> Path:
    """Copy an audio file into the cache. Returns the cached path."""
    import shutil

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = cache_path(key)
    shutil.copy2(str(audio_path), str(dest))
    return dest


def cache_evict() -> None:
    """Evict oldest files if cache exceeds MAX_CACHED."""
    if not _CACHE_DIR.exists():
        return

    files = sorted(_CACHE_DIR.glob("*.audio"), key=lambda p: p.stat().st_mtime)
    excess = len(files) - _MAX_CACHED
    if excess <= 0:
        return

    for f in files[:excess]:
        f.unlink(missing_ok=True)
    logger.debug("TTS cache: evicted %d files (kept %d)", excess, _MAX_CACHED)
