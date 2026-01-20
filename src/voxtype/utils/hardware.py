"""Hardware detection utilities."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


def is_apple_silicon() -> bool:
    """Check if running on Apple Silicon."""
    if sys.platform != "darwin":
        return False
    import platform
    return platform.machine() == "arm64"


def is_mlx_available() -> bool:
    """Check if MLX is available for Apple Silicon acceleration.

    Uses importlib to check package availability without importing it,
    avoiding the slow import of mlx_whisper during startup.
    """
    if not is_apple_silicon():
        return False
    try:
        from importlib.util import find_spec
        return find_spec("mlx_whisper") is not None
    except (ImportError, ModuleNotFoundError):
        return False


def is_cuda_available() -> bool:
    """Check if CUDA is available for GPU acceleration."""
    if sys.platform != "linux":
        return False
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except (ImportError, RuntimeError, AttributeError):
        return False


def setup_cuda_library_path() -> None:
    """Set up CUDA libraries by preloading them before ctranslate2.

    This needs to be called before importing ctranslate2 to ensure
    CUDA libraries are properly loaded.
    """
    # Find nvidia packages in site-packages
    for path in sys.path:
        nvidia_path = Path(path) / "nvidia"
        if nvidia_path.exists():
            # Preload cudnn and cublas libraries
            lib_files = [
                ("cudnn", "libcudnn.so.9"),
                ("cudnn", "libcudnn_ops.so.9"),
                ("cudnn", "libcudnn_cnn.so.9"),
                ("cublas", "libcublas.so.12"),
                ("cublas", "libcublasLt.so.12"),
            ]
            for subdir, libname in lib_files:
                lib_path = nvidia_path / subdir / "lib" / libname
                if lib_path.exists():
                    try:
                        ctypes.CDLL(str(lib_path), mode=ctypes.RTLD_GLOBAL)
                    except OSError:
                        pass  # Library already loaded or not needed

            # Also set LD_LIBRARY_PATH for any remaining libs
            lib_paths = []
            for subdir in ["cudnn", "cublas", "cuda_runtime"]:
                lib_dir = nvidia_path / subdir / "lib"
                if lib_dir.exists():
                    lib_paths.append(str(lib_dir))

            if lib_paths:
                current = os.environ.get("LD_LIBRARY_PATH", "")
                new_paths = ":".join(lib_paths)
                if current:
                    os.environ["LD_LIBRARY_PATH"] = f"{new_paths}:{current}"
                else:
                    os.environ["LD_LIBRARY_PATH"] = new_paths
            break


def is_virtualized_macos() -> bool:
    """Detect if running in a virtualized macOS environment (UTM, Parallels, VMware, etc.).

    Returns:
        True if running in a VM, False otherwise.
    """
    if sys.platform != "darwin":
        return False

    try:
        import subprocess

        # Method 1: Check CPU brand string for VM indicators
        # When running IN a VM, CPU brand often contains "Virtual" or "QEMU"
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        cpu_brand = result.stdout.strip().lower()

        vm_indicators = ["virtual", "qemu", "kvm"]
        if any(indicator in cpu_brand for indicator in vm_indicators):
            return True

        # Method 2: Check hardware model
        # Real Macs have models like "MacBookPro18,1", VMs have "VirtualMac2,1" etc.
        result = subprocess.run(
            ["sysctl", "-n", "hw.model"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        hw_model = result.stdout.strip().lower()

        if "virtual" in hw_model:
            return True

        # Method 3: Check for VM-specific platform
        # Parallels, VMware, and VirtualBox set specific platform identifiers
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.features"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        cpu_features = result.stdout.strip().lower()

        # Hypervisor feature flag indicates we're inside a VM
        # (not just that we CAN run VMs)
        if "vmm" in cpu_features:
            # VMM flag present - but this can also be on real Macs
            # Need additional confirmation
            pass

        # Method 4: Check for Apple Virtualization framework's virtual machine marker
        # This is more specific than just searching for "utm" in ioreg
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "AppleVirtualPlatform"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if "AppleVirtualPlatform" in result.stdout:
            return True

    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass

    return False


def get_best_device() -> str:
    """Detect the best available device for STT.

    Returns:
        "mlx" for Apple Silicon with MLX, "cuda" for Linux with CUDA, "cpu" otherwise.
    """
    if is_mlx_available():
        return "mlx"
    if is_cuda_available():
        return "cuda"
    return "cpu"
