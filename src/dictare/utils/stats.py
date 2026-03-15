"""Persistent statistics storage for dictare."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict


class StatsData(TypedDict, total=False):
    """Structure for persistent stats.

    total_* fields are historical (all days up to yesterday midnight).
    current_day accumulates today's stats across engine restarts.
    True all-time total = total_* + current_day.*.
    """

    first_use: str  # ISO format datetime
    total_transcriptions: int
    total_words: int
    total_chars: int
    total_keystrokes: int  # Manual keyboard input (from dictare agent)
    total_audio_seconds: float
    total_transcription_seconds: float
    total_injection_seconds: float
    total_time_saved_seconds: float
    sessions: int
    model_load_times: dict[str, float]  # Model ID -> load time in seconds
    current_day: dict  # {date, transcriptions, words, chars, audio_seconds, ...}

def get_stats_path() -> Path:
    """Get path to stats file (~/.local/share/dictare/stats.json)."""
    data_dir = Path.home() / ".local" / "share" / "dictare"
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
        "total_keystrokes": 0,
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

def _empty_day(date: str) -> dict:
    return {
        "date": date,
        "transcriptions": 0,
        "words": 0,
        "chars": 0,
        "audio_seconds": 0.0,
        "transcription_seconds": 0.0,
        "injection_seconds": 0.0,
        "time_saved_seconds": 0.0,
    }

def get_today_baseline() -> dict:
    """Return today's persisted current_day stats, or an empty dict if none."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    stats = load_stats()
    cd = stats.get("current_day") or {}
    return cd if cd.get("date") == today_str else {}

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

    historical (total_*) = all days up to yesterday midnight.
    current_day           = today's cumulative (across engine restarts).

    Day rollover: if current_day.date != today, move it into total_* first.

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
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Set first_use if this is the first session
    if not stats.get("first_use"):
        stats["first_use"] = datetime.now().isoformat()

    # Day rollover: move previous day into historical totals
    cd = stats.get("current_day") or {}
    if cd.get("date") and cd["date"] != today_str:
        stats["total_transcriptions"] += cd.get("transcriptions", 0)
        stats["total_words"] += cd.get("words", 0)
        stats["total_chars"] += cd.get("chars", 0)
        stats["total_audio_seconds"] += cd.get("audio_seconds", 0.0)
        stats["total_transcription_seconds"] += cd.get("transcription_seconds", 0.0)
        stats["total_injection_seconds"] += cd.get("injection_seconds", 0.0)
        stats["total_time_saved_seconds"] += cd.get("time_saved_seconds", 0.0)
        cd = {}  # Reset for today

    if not cd.get("date"):
        cd = _empty_day(today_str)

    # Accumulate this session into current_day
    cd["transcriptions"] += transcriptions
    cd["words"] += words
    cd["chars"] += chars
    cd["audio_seconds"] += audio_seconds
    cd["transcription_seconds"] += transcription_seconds
    cd["injection_seconds"] += injection_seconds
    cd["time_saved_seconds"] += max(0.0, time_saved_seconds)

    stats["current_day"] = cd
    stats["sessions"] = stats.get("sessions", 0) + 1

    # Save updated stats
    save_stats(stats)

    return stats

def update_keystrokes(keystrokes: int) -> StatsData:
    """Update persistent stats with keystroke count from dictare agent.

    Args:
        keystrokes: Number of keystrokes this agent session.

    Returns:
        Updated stats data.
    """
    stats = load_stats()

    # Ensure total_keystrokes exists (for backwards compatibility)
    if "total_keystrokes" not in stats:
        stats["total_keystrokes"] = 0

    # Set first_use if this is the first use ever
    if not stats["first_use"]:
        stats["first_use"] = datetime.now().isoformat()

    # Accumulate keystrokes
    stats["total_keystrokes"] += keystrokes

    # Save updated stats
    save_stats(stats)

    return stats

# -------------------------------------------------------------------------
# Model Load Times
# -------------------------------------------------------------------------

def get_model_load_time(model_id: str) -> float | None:
    """Get historical load time for a model.

    Args:
        model_id: Model identifier (e.g., 'mlx-community/whisper-large-v3-turbo').

    Returns:
        Load time in seconds, or None if no historical data.
    """
    stats = load_stats()
    load_times = stats.get("model_load_times", {})
    return load_times.get(model_id)

def save_model_load_time(model_id: str, load_time: float) -> None:
    """Save load time for a model (cold loads only).

    Only saves if:
    - No previous time recorded, OR
    - New time >= 50% of previous (it's a cold load, possibly improved)

    Warm loads (much faster, <50% of previous) are ignored to preserve
    the cold load baseline for accurate progress estimation.

    Args:
        model_id: Model identifier.
        load_time: Load time in seconds.
    """
    stats = load_stats()

    # Ensure model_load_times exists
    if "model_load_times" not in stats:
        stats["model_load_times"] = {}

    previous_time = stats["model_load_times"].get(model_id)

    # Save if: no previous OR new time is at least 50% of previous (cold load)
    # Skip if: new time is much lower (<50%), indicating a warm load
    if previous_time is None or load_time >= previous_time * 0.5:
        stats["model_load_times"][model_id] = load_time
        save_stats(stats)
