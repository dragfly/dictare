"""Tests for model cache path resolution (faster-whisper).

Regression tests for v3.0.0a32: cached models contacted HuggingFace
on every startup. These functions resolve local paths directly.
"""

from __future__ import annotations

from unittest.mock import patch

from dictare.stt.faster_whisper import (
    _MODEL_REPOS,
    _get_cached_model_path,
    _get_turbo_model_path,
    _is_model_cached,
    _is_turbo_model_cached,
)


class TestGetCachedModelPath:
    """Test _get_cached_model_path()."""

    @patch("dictare.stt.faster_whisper.os.path.exists", return_value=True)
    @patch("dictare.stt.faster_whisper.os.path.dirname", return_value="/cache/models--Systran/snapshots/abc123")
    def test_returns_cached_path(self, mock_dirname, mock_exists) -> None:
        """Returns directory when model.bin is cached."""
        with patch("huggingface_hub.try_to_load_from_cache", return_value="/cache/models--Systran/snapshots/abc123/model.bin"):
            result = _get_cached_model_path("base")
            assert result == "/cache/models--Systran/snapshots/abc123"

    @patch("huggingface_hub.try_to_load_from_cache", return_value=None)
    def test_returns_none_when_not_cached(self, _mock) -> None:
        """Returns None when model is not in cache."""
        result = _get_cached_model_path("base")
        assert result is None

    def test_turbo_delegates_to_turbo_function(self) -> None:
        """Turbo models (repo_id=None) delegate to _get_turbo_model_path()."""
        assert _MODEL_REPOS.get("large-v3-turbo") is None
        with patch("dictare.stt.faster_whisper._get_turbo_model_path", return_value="/turbo/path") as mock:
            result = _get_cached_model_path("large-v3-turbo")
            mock.assert_called_once()
            assert result == "/turbo/path"

    def test_non_turbo_handles_import_error(self) -> None:
        """Gracefully returns None if huggingface_hub is not installed."""
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            result = _get_cached_model_path("base")
            assert result is None

    def test_unknown_model_delegates_to_turbo(self) -> None:
        """Unknown model names not in _MODEL_REPOS get None repo_id → turbo path."""
        with patch("dictare.stt.faster_whisper._get_turbo_model_path", return_value=None):
            result = _get_cached_model_path("nonexistent-model")
            assert result is None

class TestGetTurboModelPath:
    """Test _get_turbo_model_path()."""

    @patch("dictare.stt.faster_whisper.os.path.exists", return_value=True)
    @patch("dictare.stt.faster_whisper.os.path.dirname", return_value="/cache/turbo")
    def test_returns_cached_turbo_path(self, mock_dirname, mock_exists) -> None:
        """Returns directory when turbo model.bin is cached."""
        with patch("huggingface_hub.try_to_load_from_cache", return_value="/cache/turbo/model.bin"):
            result = _get_turbo_model_path()
            assert result == "/cache/turbo"

    @patch("huggingface_hub.try_to_load_from_cache", return_value=None)
    def test_returns_none_when_not_cached(self, _mock) -> None:
        """Returns None when turbo model is not cached."""
        result = _get_turbo_model_path()
        assert result is None

    def test_handles_exception_gracefully(self) -> None:
        """Returns None on any exception (network error, etc)."""
        with patch("huggingface_hub.try_to_load_from_cache", side_effect=OSError("network")):
            result = _get_turbo_model_path()
            assert result is None

class TestIsCached:
    """Test convenience boolean wrappers."""

    def test_is_model_cached_true(self) -> None:
        with patch("dictare.stt.faster_whisper._get_cached_model_path", return_value="/some/path"):
            assert _is_model_cached("base") is True

    def test_is_model_cached_false(self) -> None:
        with patch("dictare.stt.faster_whisper._get_cached_model_path", return_value=None):
            assert _is_model_cached("base") is False

    def test_is_turbo_cached_true(self) -> None:
        with patch("dictare.stt.faster_whisper._get_turbo_model_path", return_value="/turbo"):
            assert _is_turbo_model_cached() is True

    def test_is_turbo_cached_false(self) -> None:
        with patch("dictare.stt.faster_whisper._get_turbo_model_path", return_value=None):
            assert _is_turbo_model_cached() is False
