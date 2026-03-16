"""Tests for model management CLI (dictare.cli.models)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from dictare.cli.models import (
    _format_size,
    _get_configured_models,
    _load_model_registry,
    ensure_required_models,
)

# ---------------------------------------------------------------------------
# _format_size
# ---------------------------------------------------------------------------

class TestFormatSize:
    def test_bytes(self) -> None:
        assert _format_size(500) == "500 B"

    def test_kilobytes(self) -> None:
        assert _format_size(2048) == "2.0 KB"

    def test_megabytes(self) -> None:
        assert _format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self) -> None:
        assert _format_size(3 * 1024 * 1024 * 1024) == "3.0 GB"

    def test_zero(self) -> None:
        assert _format_size(0) == "0 B"

    def test_fractional_kb(self) -> None:
        assert _format_size(1536) == "1.5 KB"

    def test_boundary_kb(self) -> None:
        assert _format_size(1023) == "1023 B"
        assert _format_size(1024) == "1.0 KB"

    def test_boundary_mb(self) -> None:
        result = _format_size(1024 * 1024 - 1)
        assert "KB" in result
        assert _format_size(1024 * 1024) == "1.0 MB"

    def test_boundary_gb(self) -> None:
        result = _format_size(1024 * 1024 * 1024 - 1)
        assert "MB" in result
        assert _format_size(1024 * 1024 * 1024) == "1.0 GB"


# ---------------------------------------------------------------------------
# _load_model_registry
# ---------------------------------------------------------------------------

class TestLoadModelRegistry:
    def test_loads_returns_dict(self) -> None:
        """_load_model_registry returns a dict (may be empty or populated)."""
        result = _load_model_registry()
        assert isinstance(result, dict)

    def test_registry_keys_are_strings(self) -> None:
        result = _load_model_registry()
        for key in result:
            assert isinstance(key, str)


# ---------------------------------------------------------------------------
# _get_configured_models
# ---------------------------------------------------------------------------

class TestGetConfiguredModels:
    def _make_config(self, stt_model: str = "large-v3-turbo", tts_engine: str = "say") -> SimpleNamespace:
        return SimpleNamespace(
            stt=SimpleNamespace(model=stt_model),
            tts=SimpleNamespace(engine=tts_engine),
        )

    def test_whisper_model_mapped(self) -> None:
        config = self._make_config(stt_model="large-v3-turbo")
        registry = {
            "whisper-large-v3-turbo": {"type": "stt", "repo": "r", "size_gb": 1},
        }
        with patch("dictare.cli.models._get_model_registry", return_value=registry):
            result = _get_configured_models(config)
        assert "whisper-large-v3-turbo" in result
        assert result["whisper-large-v3-turbo"] == "stt"

    def test_parakeet_model_direct_key(self) -> None:
        config = self._make_config(stt_model="parakeet-v3")
        registry = {
            "parakeet-v3": {"type": "stt", "repo": "r", "size_gb": 1},
        }
        with patch("dictare.cli.models._get_model_registry", return_value=registry):
            result = _get_configured_models(config)
        assert "parakeet-v3" in result
        assert result["parakeet-v3"] == "stt"

    def test_tts_direct_key(self) -> None:
        config = self._make_config(tts_engine="piper")
        registry = {
            "piper": {"type": "tts", "repo": "r", "size_gb": 0.5},
        }
        with patch("dictare.cli.models._get_model_registry", return_value=registry):
            result = _get_configured_models(config)
        assert "piper" in result
        assert result["piper"] == "tts"

    def test_tts_venv_match(self) -> None:
        config = self._make_config(tts_engine="coqui")
        registry = {
            "coqui-xtts-v2": {"type": "tts", "repo": "r", "size_gb": 2, "venv": "coqui"},
        }
        with patch("dictare.cli.models._get_model_registry", return_value=registry):
            result = _get_configured_models(config)
        assert "coqui-xtts-v2" in result
        assert result["coqui-xtts-v2"] == "tts"

    def test_no_matching_models(self) -> None:
        config = self._make_config(stt_model="unknown", tts_engine="unknown")
        registry = {}
        with patch("dictare.cli.models._get_model_registry", return_value=registry):
            result = _get_configured_models(config)
        assert result == {}


# ---------------------------------------------------------------------------
# ensure_required_models
# ---------------------------------------------------------------------------

class TestEnsureRequiredModels:
    def test_all_cached_returns_true(self) -> None:
        config = SimpleNamespace(
            stt=SimpleNamespace(model="base"),
            tts=SimpleNamespace(engine="say"),
        )
        registry = {
            "whisper-base": {"type": "stt", "repo": "openai/whisper-base", "size_gb": 0.1, "check_file": "config.json"},
        }
        with patch("dictare.cli.models._get_model_registry", return_value=registry), \
             patch("dictare.cli.models._get_configured_models", return_value={"whisper-base": "stt"}), \
             patch("dictare.utils.hf_download.is_repo_cached", return_value=True):
            assert ensure_required_models(config) is True

    def test_missing_model_downloads(self) -> None:
        config = SimpleNamespace(
            stt=SimpleNamespace(model="base"),
            tts=SimpleNamespace(engine="say"),
        )
        registry = {
            "whisper-base": {
                "type": "stt",
                "repo": "openai/whisper-base",
                "size_gb": 0.1,
                "description": "Whisper Base",
            },
        }
        with patch("dictare.cli.models._get_model_registry", return_value=registry), \
             patch("dictare.cli.models._get_configured_models", return_value={"whisper-base": "stt"}), \
             patch("dictare.utils.hf_download.is_repo_cached", return_value=False), \
             patch("dictare.utils.hf_download.download_with_progress") as mock_dl, \
             patch("dictare.cli.models.console"):
            result = ensure_required_models(config)
        assert result is True
        mock_dl.assert_called_once()

    def test_download_failure_returns_false(self) -> None:
        config = SimpleNamespace(
            stt=SimpleNamespace(model="base"),
            tts=SimpleNamespace(engine="say"),
        )
        registry = {
            "whisper-base": {
                "type": "stt",
                "repo": "openai/whisper-base",
                "size_gb": 0.1,
                "description": "Whisper Base",
            },
        }
        with patch("dictare.cli.models._get_model_registry", return_value=registry), \
             patch("dictare.cli.models._get_configured_models", return_value={"whisper-base": "stt"}), \
             patch("dictare.utils.hf_download.is_repo_cached", return_value=False), \
             patch("dictare.utils.hf_download.download_with_progress", side_effect=RuntimeError("network")), \
             patch("dictare.cli.models.console"):
            result = ensure_required_models(config)
        assert result is False

    def test_no_repo_skipped(self) -> None:
        config = SimpleNamespace(
            stt=SimpleNamespace(model="base"),
            tts=SimpleNamespace(engine="say"),
        )
        registry = {
            "builtin-say": {"type": "tts", "builtin": True},
        }
        with patch("dictare.cli.models._get_model_registry", return_value=registry), \
             patch("dictare.cli.models._get_configured_models", return_value={"builtin-say": "tts"}), \
             patch("dictare.utils.hf_download.is_repo_cached") as mock_cached:
            result = ensure_required_models(config)
        assert result is True
        mock_cached.assert_not_called()
