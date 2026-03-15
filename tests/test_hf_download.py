"""Tests for utils/hf_download.py — HuggingFace download utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from dictare.utils.hf_download import (
    DownloadProgressMonitor,
    get_cache_size,
    get_hf_cache_dir,
)


class TestGetHfCacheDir:
    def test_simple_repo(self) -> None:
        path = get_hf_cache_dir("openai/whisper-large-v3")
        assert path.name == "models--openai--whisper-large-v3"
        assert ".cache/huggingface/hub" in str(path)

    def test_nested_repo(self) -> None:
        path = get_hf_cache_dir("org/sub/model")
        assert path.name == "models--org--sub--model"


class TestGetCacheSize:
    def test_returns_zero_when_dir_missing(self) -> None:
        with patch.object(Path, "exists", return_value=False):
            size = get_cache_size("nonexistent/repo")
        assert size == 0

    def test_sums_file_sizes(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "models--test--repo"
        repo_dir.mkdir(parents=True)
        (repo_dir / "file1.bin").write_bytes(b"x" * 100)
        (repo_dir / "file2.bin").write_bytes(b"y" * 200)

        with patch("dictare.utils.hf_download.get_hf_cache_dir", return_value=repo_dir):
            size = get_cache_size("test/repo")
        assert size == 300


class TestDownloadProgressMonitor:
    def test_context_manager_starts_and_stops(self) -> None:
        progress = MagicMock()
        task_id = MagicMock()

        monitor = DownloadProgressMonitor(
            "test/repo", 1000, progress, task_id, interval=0.01,
        )

        with monitor:
            assert monitor._thread is not None
            assert monitor._thread.is_alive()

        # After exit, thread should stop
        assert not monitor._thread.is_alive()
        # Progress should be set to 100%
        progress.update.assert_called_with(task_id, completed=1000)

    def test_stop_is_idempotent(self) -> None:
        progress = MagicMock()
        monitor = DownloadProgressMonitor(
            "test/repo", 1000, progress, MagicMock(), interval=0.01,
        )
        monitor.stop()  # Should not raise even without start
