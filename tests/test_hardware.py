"""Tests for hardware detection utilities."""

from __future__ import annotations

from unittest.mock import patch

from voxtype.config import Config
from voxtype.utils.hardware import (
    auto_detect_acceleration,
    detect_nvidia_gpu,
    get_best_device,
)

class TestAutoDetectAcceleration:
    """Test auto_detect_acceleration()."""

    def _make_config(self, device: str = "auto") -> Config:
        """Create a Config with stt.device set."""
        config = Config()
        config.stt.advanced.device = device
        return config

    def test_cpu_only_forces_cpu(self) -> None:
        """cpu_only=True forces CPU regardless of available hardware."""
        config = self._make_config()
        auto_detect_acceleration(config, cpu_only=True)
        assert config.stt.advanced.device == "cpu"
        assert config.stt.advanced.compute_type == "int8"

    def test_skips_detection_when_device_not_auto(self) -> None:
        """Does nothing when device is already set (not 'auto')."""
        config = self._make_config(device="cuda")
        auto_detect_acceleration(config)
        assert config.stt.advanced.device == "cuda"

    @patch("voxtype.utils.hardware.is_virtualized_macos", return_value=False)
    @patch("voxtype.utils.hardware.is_mlx_available", return_value=True)
    def test_mlx_sets_device_to_mlx(self, _mock_mlx, _mock_vm) -> None:
        """When MLX is available, device must be set to 'mlx' (not left as 'cpu')."""
        config = self._make_config()
        auto_detect_acceleration(config)
        assert config.stt.advanced.device == "mlx"

    @patch("voxtype.utils.hardware.is_virtualized_macos", return_value=False)
    @patch("voxtype.utils.hardware.is_mlx_available", return_value=False)
    @patch("voxtype.utils.hardware.is_cuda_available", return_value=True)
    @patch("voxtype.utils.hardware.setup_cuda_library_path")
    def test_cuda_sets_device_and_compute_type(self, _mock_setup, _mock_cuda, _mock_mlx, _mock_vm) -> None:
        """When CUDA is available, device='cuda' and compute_type='float16'."""
        config = self._make_config()
        auto_detect_acceleration(config)
        assert config.stt.advanced.device == "cuda"
        assert config.stt.advanced.compute_type == "float16"

    @patch("voxtype.utils.hardware.is_virtualized_macos", return_value=False)
    @patch("voxtype.utils.hardware.is_mlx_available", return_value=False)
    @patch("voxtype.utils.hardware.is_cuda_available", return_value=False)
    def test_fallback_to_cpu(self, _mock_cuda, _mock_mlx, _mock_vm) -> None:
        """When nothing is available, falls back to CPU."""
        config = self._make_config()
        auto_detect_acceleration(config)
        assert config.stt.advanced.device == "cpu"

    @patch("voxtype.utils.hardware.is_virtualized_macos", return_value=True)
    def test_virtualized_macos_forces_cpu(self, _mock_vm) -> None:
        """Virtualized macOS disables hardware acceleration."""
        config = self._make_config()
        auto_detect_acceleration(config)
        assert config.stt.advanced.device == "cpu"
        assert config.stt.hw_accel is False

class TestDetectNvidiaGpu:
    """Test detect_nvidia_gpu() subprocess calls."""

    @patch("voxtype.utils.hardware.sys")
    def test_non_linux_returns_none(self, mock_sys) -> None:
        """Non-Linux always returns 'none'."""
        mock_sys.platform = "darwin"
        assert detect_nvidia_gpu() == "none"

    @patch("voxtype.utils.hardware.sys")
    @patch("subprocess.run")
    def test_gpu_found(self, mock_run, mock_sys) -> None:
        """Returns 'found' when nvidia-smi detects a GPU."""
        mock_sys.platform = "linux"
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b"NVIDIA GeForce RTX 4090\n"
        assert detect_nvidia_gpu() == "found"

    @patch("voxtype.utils.hardware.sys")
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_nvidia_smi_not_installed(self, _mock_run, mock_sys) -> None:
        """Returns 'no_tool' when nvidia-smi is not found."""
        mock_sys.platform = "linux"
        assert detect_nvidia_gpu() == "no_tool"

    @patch("voxtype.utils.hardware.sys")
    @patch("subprocess.run")
    def test_no_gpu_detected(self, mock_run, mock_sys) -> None:
        """Returns 'none' when nvidia-smi runs but finds no GPU."""
        mock_sys.platform = "linux"
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b""
        assert detect_nvidia_gpu() == "none"

class TestGetBestDevice:
    """Test get_best_device() helper."""

    @patch("voxtype.utils.hardware.is_mlx_available", return_value=True)
    def test_prefers_mlx(self, _mock) -> None:
        assert get_best_device() == "mlx"

    @patch("voxtype.utils.hardware.is_mlx_available", return_value=False)
    @patch("voxtype.utils.hardware.is_cuda_available", return_value=True)
    def test_prefers_cuda_over_cpu(self, _mock_cuda, _mock_mlx) -> None:
        assert get_best_device() == "cuda"

    @patch("voxtype.utils.hardware.is_mlx_available", return_value=False)
    @patch("voxtype.utils.hardware.is_cuda_available", return_value=False)
    def test_falls_back_to_cpu(self, _mock_cuda, _mock_mlx) -> None:
        assert get_best_device() == "cpu"
