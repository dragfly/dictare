"""Model loading indicator with progress tracking.

Shows elapsed time during model loading, and uses historical data
for progress bar estimates on subsequent runs.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

def load_with_indicator(
    model_id: str,
    model_name: str,
    load_fn: Callable[[], T],
    console: Any | None = None,
    *,
    headless: bool = False,
) -> T:
    """Load a model with progress bar or elapsed time indicator.

    If historical cold load time exists, shows a progress bar with ETA.
    Otherwise, shows elapsed time. Only cold load times are saved
    (warm loads are ignored to preserve accurate baseline).

    Args:
        model_id: Model identifier for stats (e.g., 'mlx-community/whisper-large-v3-turbo').
        model_name: Display name (e.g., 'STT model', 'VAD model').
        load_fn: Function that loads the model.
        console: Optional Rich Console instance.
        headless: If True, skip all console output (for Engine/daemon mode).

    Returns:
        Result of load_fn().

    Example:
        model = load_with_indicator(
            "mlx-community/whisper-large-v3-turbo",
            "STT model",
            lambda: ModelHolder.get_model(path, mx.float16),
        )
    """
    from voxtype.utils.stats import get_model_load_time, save_model_load_time

    # Headless mode: just load and save stats, no console output
    if headless:
        start_time = time.time()
        result = load_fn()
        load_time = time.time() - start_time
        save_model_load_time(model_id, load_time)
        return result

    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )

    if console is None:
        console = Console()

    # Check for historical cold load time
    historical_time = get_model_load_time(model_id)

    start_time = time.time()

    if historical_time is not None:
        # We have historical cold time - show progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Loading {model_name}...", total=historical_time)

            # Monitor thread updates progress based on elapsed time
            stop_event = threading.Event()

            def update_progress():
                while not stop_event.is_set():
                    elapsed = time.time() - start_time
                    # Cap at 99% until load_fn completes
                    completed = min(elapsed, historical_time * 0.99)
                    progress.update(task, completed=completed)
                    time.sleep(0.1)

            thread = threading.Thread(target=update_progress, daemon=True)
            thread.start()

            try:
                result = load_fn()
            finally:
                stop_event.set()
                thread.join(timeout=1)
                progress.update(task, completed=historical_time)
    else:
        # No historical data - show elapsed time
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(f"Loading {model_name}...", total=None)
            result = load_fn()

    # Calculate and save load time (only cold loads are saved)
    load_time = time.time() - start_time
    save_model_load_time(model_id, load_time)

    # Show completion message
    console.print(f"[green]✓[/] {model_name} loaded in {load_time:.1f}s")

    return result
