"""Tests for StatusPanel display logic."""

from __future__ import annotations

from dictare.cli.panel import StatusPanel

def _make_status(*, state: str = "off", device: str = "cpu", model: str = "large-v3-turbo") -> dict:
    """Build a realistic /status response for testing."""
    return {
        "protocol_version": "1.0",
        "state": state,
        "connected_agents": [],
        "uptime_seconds": 0,
        "platform": {
            "name": "Dictare",
            "version": "3.0.0-test",
            "mode": "keyboard",
            "state": state,
            "uptime_seconds": 0,
            "stt": {
                "model_name": model,
                "device": device,
                "last_text": "",
            },
            "output": {
                "mode": "keyboard",
                "current_agent": None,
                "available_agents": [],
            },
            "hotkey": {"key": "cmd", "bound": True},
            "loading": {"active": False, "models": []},
        },
    }

class TestPanelState:
    """Test that panel reads state correctly from status response."""

    def test_state_read_from_platform_not_stt(self) -> None:
        """Panel must read state from platform.state, not platform.stt.state.

        Regression test for v3.0.0a36: panel always showed OFF because it
        read from the wrong path in the status dict.
        """
        panel = StatusPanel(console=None, base_url="http://127.0.0.1:0")
        panel._status = _make_status(state="recording")
        built = panel._build_panel()
        # The rendered panel text must contain RECORDING, not OFF
        rendered = built.renderable.plain if hasattr(built.renderable, "plain") else str(built.renderable)
        assert "RECORDING" in rendered.upper()
        assert "OFF" not in rendered.upper()

    def test_off_state(self) -> None:
        """Panel shows OFF when state is off."""
        panel = StatusPanel(console=None, base_url="http://127.0.0.1:0")
        panel._status = _make_status(state="off")
        built = panel._build_panel()
        rendered = built.renderable.plain if hasattr(built.renderable, "plain") else str(built.renderable)
        assert "OFF" in rendered.upper()

class TestPanelDevice:
    """Test that panel displays device names correctly."""

    def test_mlx_device_display(self) -> None:
        """Panel must show 'MLX (Apple Silicon)' for mlx device.

        Regression test for v3.0.0a34: mlx was missing from the device
        mapping, causing a fallback to platform heuristic.
        """
        panel = StatusPanel(console=None, base_url="http://127.0.0.1:0")
        panel._status = _make_status(device="mlx")
        built = panel._build_panel()
        rendered = built.renderable.plain if hasattr(built.renderable, "plain") else str(built.renderable)
        assert "MLX" in rendered

    def test_cuda_device_display(self) -> None:
        """Panel shows 'GPU (CUDA)' for cuda device."""
        panel = StatusPanel(console=None, base_url="http://127.0.0.1:0")
        panel._status = _make_status(device="cuda")
        built = panel._build_panel()
        rendered = built.renderable.plain if hasattr(built.renderable, "plain") else str(built.renderable)
        assert "CUDA" in rendered

    def test_cpu_device_display(self) -> None:
        """Panel shows 'CPU' for cpu device."""
        panel = StatusPanel(console=None, base_url="http://127.0.0.1:0")
        panel._status = _make_status(device="cpu")
        built = panel._build_panel()
        rendered = built.renderable.plain if hasattr(built.renderable, "plain") else str(built.renderable)
        assert "CPU" in rendered
