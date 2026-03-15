"""Tests for utils/loading.py — load_with_indicator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dictare.utils.loading import load_with_indicator


class TestLoadWithIndicatorHeadless:
    @patch("dictare.utils.stats.save_model_load_time")
    @patch("dictare.utils.stats.get_model_load_time", return_value=None)
    def test_headless_returns_result(self, mock_get, mock_save) -> None:
        result = load_with_indicator(
            "test-model",
            "Test Model",
            lambda: "loaded-value",
            headless=True,
        )
        assert result == "loaded-value"

    @patch("dictare.utils.stats.save_model_load_time")
    @patch("dictare.utils.stats.get_model_load_time", return_value=None)
    def test_headless_saves_load_time(self, mock_get, mock_save) -> None:
        load_with_indicator(
            "test-model",
            "Test Model",
            lambda: "value",
            headless=True,
        )
        mock_save.assert_called_once()
        args = mock_save.call_args[0]
        assert args[0] == "test-model"
        assert isinstance(args[1], float)
        assert args[1] >= 0

    @patch("dictare.utils.stats.save_model_load_time")
    @patch("dictare.utils.stats.get_model_load_time", return_value=None)
    def test_headless_propagates_exception(self, mock_get, mock_save) -> None:
        import pytest

        def explode():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            load_with_indicator(
                "test-model",
                "Test Model",
                explode,
                headless=True,
            )


class TestLoadWithIndicatorVisual:
    @patch("dictare.utils.stats.save_model_load_time")
    @patch("dictare.utils.stats.get_model_load_time", return_value=None)
    def test_no_historical_time_returns_result(self, mock_get, mock_save) -> None:
        console = MagicMock()
        result = load_with_indicator(
            "test-model",
            "Test Model",
            lambda: 42,
            console=console,
        )
        assert result == 42
        mock_save.assert_called_once()

    @patch("dictare.utils.stats.save_model_load_time")
    @patch("dictare.utils.stats.get_model_load_time", return_value=2.0)
    def test_with_historical_time_returns_result(self, mock_get, mock_save) -> None:
        # Use a real Rich Console (stderr) since Rich Progress internals
        # don't work with MagicMock timestamps
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO(), quiet=True)
        result = load_with_indicator(
            "test-model",
            "Test Model",
            lambda: "fast-result",
            console=console,
        )
        assert result == "fast-result"
        mock_save.assert_called_once()
