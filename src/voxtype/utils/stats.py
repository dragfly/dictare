"""Persistent statistics storage for voxtype."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict


class StatsData(TypedDict):
    """Structure for persistent stats."""

    first_use: str  # ISO format datetime
    total_transcriptions: int
    total_words: int
    total_chars: int
    total_audio_seconds: float
    total_transcription_seconds: float
    total_injection_seconds: float
    total_time_saved_seconds: float
    sessions: int


def get_stats_path() -> Path:
    """Get path to stats file (~/.local/share/voxtype/stats.json)."""
    data_dir = Path.home() / ".local" / "share" / "voxtype"
    return data_dir / "stats.json"


def load_stats() -> StatsData:
    """Load persistent stats from disk.

    Returns:
        Stats data, or empty stats if file doesn't exist.
    """
    stats_path = get_stats_path()

    if stats_path.exists():
        try:
            with open(stats_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            pass  # Return empty stats on error

    # Return empty stats
    return {
        "first_use": "",
        "total_transcriptions": 0,
        "total_words": 0,
        "total_chars": 0,
        "total_audio_seconds": 0.0,
        "total_transcription_seconds": 0.0,
        "total_injection_seconds": 0.0,
        "total_time_saved_seconds": 0.0,
        "sessions": 0,
    }


def save_stats(stats: StatsData) -> None:
    """Save persistent stats to disk.

    Args:
        stats: Stats data to save.
    """
    stats_path = get_stats_path()

    # Create directory if needed
    stats_path.parent.mkdir(parents=True, exist_ok=True)

    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)


def update_stats(
    transcriptions: int,
    words: int,
    chars: int,
    audio_seconds: float,
    transcription_seconds: float,
    injection_seconds: float,
    time_saved_seconds: float,
) -> StatsData:
    """Update persistent stats with session data.

    Args:
        transcriptions: Number of transcriptions this session.
        words: Number of words this session.
        chars: Number of characters this session.
        audio_seconds: Audio duration this session.
        transcription_seconds: STT processing time this session.
        injection_seconds: Text injection time this session.
        time_saved_seconds: Time saved this session.

    Returns:
        Updated stats data.
    """
    stats = load_stats()

    # Set first_use if this is the first session
    if not stats["first_use"]:
        stats["first_use"] = datetime.now().isoformat()

    # Accumulate session stats
    stats["total_transcriptions"] += transcriptions
    stats["total_words"] += words
    stats["total_chars"] += chars
    stats["total_audio_seconds"] += audio_seconds
    stats["total_transcription_seconds"] += transcription_seconds
    stats["total_injection_seconds"] += injection_seconds
    stats["total_time_saved_seconds"] += time_saved_seconds
    stats["sessions"] += 1

    # Save updated stats
    save_stats(stats)

    return stats
