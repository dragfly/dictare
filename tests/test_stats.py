"""Tests for utils/stats.py: update_keystrokes, model load time functions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from dictare.utils.stats import (
    get_model_load_time,
    load_stats,
    save_model_load_time,
    save_stats,
    update_keystrokes,
    update_stats,
)


def _empty_stats():
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


# ---------------------------------------------------------------------------
# load_stats / save_stats round-trip
# ---------------------------------------------------------------------------


class TestLoadSaveStats:
    def test_load_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            stats = load_stats()
        assert stats["total_transcriptions"] == 0
        assert stats["sessions"] == 0

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        data = _empty_stats()
        data["sessions"] = 7
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            save_stats(data)
            loaded = load_stats()
        assert loaded["sessions"] == 7

    def test_load_returns_empty_on_corrupt_json(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        p.write_text("not valid json")
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            stats = load_stats()
        assert stats["total_transcriptions"] == 0


# ---------------------------------------------------------------------------
# update_keystrokes
# ---------------------------------------------------------------------------


class TestUpdateKeystrokes:
    def test_increments_from_zero(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            result = update_keystrokes(50)
        assert result["total_keystrokes"] == 50

    def test_accumulates_across_calls(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            update_keystrokes(30)
            update_keystrokes(20)
            result = update_keystrokes(5)
        assert result["total_keystrokes"] == 55

    def test_sets_first_use_when_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            result = update_keystrokes(1)
        assert result["first_use"] != ""

    def test_preserves_first_use_if_set(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        initial = _empty_stats()
        initial["first_use"] = "2026-01-01T00:00:00"
        p.parent.mkdir(parents=True, exist_ok=True)
        import json
        p.write_text(json.dumps(initial))
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            result = update_keystrokes(10)
        assert result["first_use"] == "2026-01-01T00:00:00"

    def test_creates_total_keystrokes_if_missing(self, tmp_path: Path) -> None:
        """Handles stats files that predate the total_keystrokes field."""
        p = tmp_path / "stats.json"
        initial = _empty_stats()
        del initial["total_keystrokes"]
        import json
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(initial))
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            result = update_keystrokes(100)
        assert result["total_keystrokes"] == 100


# ---------------------------------------------------------------------------
# update_stats
# ---------------------------------------------------------------------------


class TestUpdateStats:
    def test_accumulates_transcriptions(self, tmp_path: Path) -> None:
        """Same-day calls accumulate in current_day, not total_* (historical)."""
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            update_stats(5, 50, 300, 10.0, 2.0, 0.5, 8.0)
            result = update_stats(3, 20, 100, 5.0, 1.0, 0.2, 4.0)
        assert result["current_day"]["transcriptions"] == 8
        assert result["total_transcriptions"] == 0  # historical unchanged (no day rollover)
        assert result["sessions"] == 2

    def test_increments_sessions(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            for _ in range(3):
                update_stats(1, 1, 1, 1.0, 1.0, 1.0, 1.0)
            result = load_stats()
        assert result["sessions"] == 3

    def test_day_rollover(self, tmp_path: Path) -> None:
        """When saving on a new day, previous current_day moves into total_*."""
        import json
        from datetime import timedelta
        p = tmp_path / "stats.json"
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        # Write a stats file with yesterday's current_day
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "first_use": "",
            "total_transcriptions": 0, "total_words": 0, "total_chars": 0,
            "total_keystrokes": 0, "total_audio_seconds": 0.0,
            "total_transcription_seconds": 0.0, "total_injection_seconds": 0.0,
            "total_time_saved_seconds": 0.0, "sessions": 0,
            "current_day": {"date": yesterday, "transcriptions": 5, "words": 40,
                            "chars": 200, "audio_seconds": 8.0,
                            "transcription_seconds": 2.0, "injection_seconds": 0.5,
                            "time_saved_seconds": 6.0},
        }))
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            result = update_stats(3, 20, 100, 5.0, 1.0, 0.2, 4.0)
        # Yesterday's current_day rolled into historical
        assert result["total_transcriptions"] == 5
        assert result["total_words"] == 40
        # Today's session is in current_day
        today = datetime.now().strftime("%Y-%m-%d")
        assert result["current_day"]["date"] == today
        assert result["current_day"]["transcriptions"] == 3


# ---------------------------------------------------------------------------
# get_model_load_time / save_model_load_time
# ---------------------------------------------------------------------------


class TestModelLoadTime:
    def test_returns_none_when_no_data(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            result = get_model_load_time("mlx-community/whisper-large-v3-turbo")
        assert result is None

    def test_save_and_retrieve(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            save_model_load_time("my-model", 12.5)
            result = get_model_load_time("my-model")
        assert result == 12.5

    def test_warm_load_is_ignored(self, tmp_path: Path) -> None:
        """Load time < 50% of previous is treated as warm load and not saved."""
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            save_model_load_time("model", 10.0)
            save_model_load_time("model", 4.9)  # 49% of 10.0 → ignored
            result = get_model_load_time("model")
        assert result == 10.0

    def test_cold_load_at_50_percent_is_saved(self, tmp_path: Path) -> None:
        """Load time >= 50% of previous is saved (still counts as cold load)."""
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            save_model_load_time("model", 10.0)
            save_model_load_time("model", 5.0)  # exactly 50% → saved
            result = get_model_load_time("model")
        assert result == 5.0

    def test_first_save_always_stored(self, tmp_path: Path) -> None:
        """Very fast first-ever load is still stored (no previous to compare)."""
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            save_model_load_time("new-model", 0.1)
            result = get_model_load_time("new-model")
        assert result == 0.1

    def test_different_models_stored_independently(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            save_model_load_time("model-a", 5.0)
            save_model_load_time("model-b", 8.0)
            assert get_model_load_time("model-a") == 5.0
            assert get_model_load_time("model-b") == 8.0

    def test_unknown_model_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "stats.json"
        with patch("dictare.utils.stats.get_stats_path", return_value=p):
            save_model_load_time("model-a", 5.0)
            assert get_model_load_time("model-z") is None
