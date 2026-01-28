"""HuggingFace model download with real progress monitoring.

Monitors the cache directory size to show accurate download progress,
since huggingface_hub doesn't provide good progress callbacks.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def get_hf_cache_dir(repo_id: str) -> Path:
    """Get the HuggingFace cache directory for a repo.

    Args:
        repo_id: HuggingFace repo ID (e.g., 'lucasnewman/f5-tts-mlx').

    Returns:
        Path to the cache directory.
    """
    cache_dir = Path.home() / ".cache/huggingface/hub"
    repo_dir_name = f"models--{repo_id.replace('/', '--')}"
    return cache_dir / repo_dir_name


def get_cache_size(repo_id: str) -> int:
    """Get current size of cached repo in bytes.

    Args:
        repo_id: HuggingFace repo ID.

    Returns:
        Total size of cached files in bytes.
    """
    repo_path = get_hf_cache_dir(repo_id)
    if not repo_path.exists():
        return 0
    try:
        return sum(f.stat().st_size for f in repo_path.rglob("*") if f.is_file())
    except Exception:
        return 0


def get_repo_size(repo_id: str) -> int | None:
    """Get expected total size from HuggingFace API.

    Args:
        repo_id: HuggingFace repo ID.

    Returns:
        Total size in bytes, or None if unavailable.
    """
    try:
        from huggingface_hub import HfApi

        api = HfApi()
        info = api.repo_info(repo_id, repo_type="model")
        if info.siblings:
            return sum(s.size or 0 for s in info.siblings)
    except Exception:
        pass
    return None


def is_repo_cached(repo_id: str, check_file: str = "config.json") -> bool:
    """Check if a HuggingFace repo is already cached.

    Args:
        repo_id: HuggingFace repo ID.
        check_file: A file to check for (proves download is complete).

    Returns:
        True if the model is cached.
    """
    try:
        from huggingface_hub import try_to_load_from_cache

        result = try_to_load_from_cache(repo_id, check_file)
        return result is not None
    except Exception:
        return False


class DownloadProgressMonitor:
    """Background thread that monitors download progress via cache size.

    Usage:
        with DownloadProgressMonitor(repo_id, expected_size, progress, task_id):
            model = load_model(repo_id)
    """

    def __init__(
        self,
        repo_id: str,
        expected_size: int,
        progress: Any,
        task_id: Any,
        interval: float = 0.5,
    ):
        """Initialize the monitor.

        Args:
            repo_id: HuggingFace repo ID to monitor.
            expected_size: Expected total download size in bytes.
            progress: Rich Progress instance.
            task_id: Task ID from progress.add_task().
            interval: Polling interval in seconds.
        """
        self.repo_id = repo_id
        self.expected_size = expected_size
        self.progress = progress
        self.task_id = task_id
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        """Start monitoring in background thread."""
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop monitoring."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        self.stop()
        # Set to 100% on completion
        self.progress.update(self.task_id, completed=self.expected_size)

    def _monitor(self):
        """Monitor cache size and update progress."""
        while not self._stop.is_set():
            current_size = get_cache_size(self.repo_id)
            self.progress.update(self.task_id, completed=current_size)
            time.sleep(self.interval)


def download_with_progress(
    repo_id: str,
    load_fn: Callable[[], T],
    fallback_size_gb: float = 1.0,
    console: Any | None = None,
) -> T:
    """Download a HuggingFace model with real progress bar.

    Args:
        repo_id: HuggingFace repo ID (e.g., 'lucasnewman/f5-tts-mlx').
        load_fn: Function that loads/downloads the model.
        fallback_size_gb: Fallback size in GB if API call fails.
        console: Optional Rich Console instance.

    Returns:
        Result of load_fn().

    Example:
        model = download_with_progress(
            "lucasnewman/f5-tts-mlx",
            lambda: load_model("lucasnewman/f5-tts-mlx"),
            fallback_size_gb=4.0,
        )
    """
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )

    if console is None:
        console = Console()

    # Check if already cached
    if is_repo_cached(repo_id):
        return load_fn()

    # Get expected size
    expected_size = get_repo_size(repo_id)
    if expected_size is None:
        expected_size = int(fallback_size_gb * 1024 * 1024 * 1024)

    console.print(f"[cyan]Downloading model ({expected_size / 1e9:.1f} GB)...[/]")
    console.print(f"[dim]Source: huggingface.co/{repo_id}[/]")

    # Suppress huggingface's progress bars
    from huggingface_hub.utils import disable_progress_bars, enable_progress_bars

    disable_progress_bars()

    try:
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading", total=expected_size)

            with DownloadProgressMonitor(repo_id, expected_size, progress, task):
                result = load_fn()

        console.print("[green]✓ Model ready[/]")
        return result

    finally:
        enable_progress_bars()
