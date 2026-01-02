"""CUDA/cuDNN setup utilities.

Handles automatic library loading and provides clear error messages.
"""

from __future__ import annotations

import ctypes
import glob
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

def _find_cudnn_path() -> str | None:
    """Find the nvidia-cudnn library path in the current environment.

    Returns:
        Path to cudnn/lib directory, or None if not found.
    """
    # Standard location for pip-installed nvidia-cudnn-cu12
    patterns = [
        # In virtual environment
        os.path.join(sys.prefix, "lib", "python*", "site-packages", "nvidia", "cudnn", "lib"),
        # In user site-packages
        os.path.expanduser("~/.local/lib/python*/site-packages/nvidia/cudnn/lib"),
    ]

    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            # Return first match that exists and has libraries
            for path in matches:
                if os.path.isdir(path) and glob.glob(os.path.join(path, "libcudnn*.so*")):
                    return path

    return None

def _preload_cudnn_libraries(cudnn_path: str) -> tuple[bool, str | None]:
    """Pre-load cuDNN libraries before importing ctranslate2.

    Args:
        cudnn_path: Path to the cudnn/lib directory.

    Returns:
        Tuple of (success, error_message).
    """
    # Libraries to load in order (dependencies first)
    required_libs = [
        "libcudnn.so.9",
        "libcudnn_ops.so.9",
        "libcudnn_cnn.so.9",
        "libcudnn_adv.so.9",
        "libcudnn_graph.so.9",
        "libcudnn_engines_runtime_compiled.so.9",
        "libcudnn_engines_precompiled.so.9",
        "libcudnn_heuristic.so.9",
    ]

    loaded = []
    for lib_name in required_libs:
        lib_path = os.path.join(cudnn_path, lib_name)
        if os.path.exists(lib_path):
            try:
                ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)
                loaded.append(lib_name)
            except OSError as e:
                return False, f"Failed to load {lib_name}: {e}"

    if not loaded:
        return False, "No cuDNN libraries found"

    return True, None

def setup_cuda(console: Console | None = None, verbose: bool = False) -> tuple[bool, str]:
    """Setup CUDA/cuDNN for GPU acceleration.

    This should be called BEFORE importing faster_whisper or ctranslate2.

    Args:
        console: Optional Rich console for output.
        verbose: If True, show detailed loading info.

    Returns:
        Tuple of (cuda_available, device_string).
        device_string is "cuda" if GPU available, "cpu" otherwise.
    """
    # Check if CUDA is available at all
    try:
        import torch
        if not torch.cuda.is_available():
            return False, "cpu"
    except ImportError:
        # No torch, try ctranslate2 directly later
        pass

    # Find cuDNN libraries
    cudnn_path = _find_cudnn_path()

    if cudnn_path is None:
        if verbose and console:
            console.print("[dim]cuDNN not found, will try GPU anyway or fall back to CPU[/]")
        return True, "cuda"  # Let ctranslate2 try, might have bundled libs

    # Pre-load cuDNN libraries
    success, error = _preload_cudnn_libraries(cudnn_path)

    if not success:
        if console:
            _print_cudnn_error(console, error, cudnn_path)
        return False, "cpu"

    if verbose and console:
        console.print(f"[dim]Loaded cuDNN from {cudnn_path}[/]")

    return True, "cuda"

def _print_cudnn_error(console: Console, error: str | None, cudnn_path: str | None) -> None:
    """Print helpful error message for cuDNN issues."""
    console.print("\n[yellow]⚠ GPU acceleration unavailable[/]")

    if error:
        console.print(f"[dim]Error: {error}[/]")

    console.print("\n[bold]To enable GPU:[/]")
    console.print("  1. Install cuDNN: [cyan]pip install 'nvidia-cudnn-cu12>=9.1.0,<9.2.0'[/]")

    if cudnn_path:
        console.print(f"\n  2. Or add to ~/.bashrc:")
        console.print(f"     [cyan]export LD_LIBRARY_PATH=\"{cudnn_path}:$LD_LIBRARY_PATH\"[/]")

    console.print("\n[dim]Falling back to CPU (slower but works)[/]\n")

def check_gpu_available() -> tuple[bool, int]:
    """Quick check if CUDA GPU is available.

    Returns:
        Tuple of (available, device_count).
    """
    try:
        # Try ctranslate2's CUDA check
        import ctranslate2
        cuda_device_count = ctranslate2.get_cuda_device_count()
        return cuda_device_count > 0, cuda_device_count
    except Exception:
        pass

    try:
        # Fallback to torch
        import torch
        if torch.cuda.is_available():
            return True, torch.cuda.device_count()
    except ImportError:
        pass

    return False, 0
