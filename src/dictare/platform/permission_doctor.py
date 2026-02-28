"""Single source of truth for permission diagnosis and guided recovery."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dictare.hotkey.runtime_status import read_runtime_status
from dictare.platform.permissions import (
    open_accessibility_settings,
    open_input_monitoring_settings,
    open_microphone_settings,
)

@dataclass
class DoctorStatus:
    accessibility: bool
    microphone: bool
    input_monitoring: bool
    hotkey_status: str
    capture_healthy: bool
    active_provider: str

class PermissionDoctor:
    """Guided permission flow with runtime hotkey probing."""

    def get_status(self) -> DoctorStatus:
        from dictare.platform.permissions import get_permissions

        perms = get_permissions()
        runtime = read_runtime_status() or {}
        hotkey_status = str(runtime.get("status", self._read_launcher_status()))
        capture_healthy = bool(runtime.get("capture_healthy", hotkey_status == "confirmed"))
        active_provider = str(runtime.get("active_provider", "none"))

        return DoctorStatus(
            accessibility=bool(perms.get("accessibility", True)),
            microphone=bool(perms.get("microphone", True)),
            input_monitoring=bool(perms.get("input_monitoring", True)),
            hotkey_status=hotkey_status,
            capture_healthy=capture_healthy,
            active_provider=active_provider,
        )

    def run_probe(self, timeout_s: float = 8.0) -> dict:
        """Wait for a new hotkey event to arrive via runtime status counters."""
        start = time.time()
        baseline = self._delivered_count()
        deadline = start + max(1.0, min(timeout_s, 30.0))

        while time.time() < deadline:
            now_count = self._delivered_count()
            if now_count > baseline:
                status = self.get_status()
                return {
                    "ok": True,
                    "message": "Hotkey event received",
                    "delivered_count": now_count,
                    "active_provider": status.active_provider,
                    "capture_healthy": status.capture_healthy,
                    "hotkey_status": status.hotkey_status,
                }
            time.sleep(0.1)

        status = self.get_status()
        return {
            "ok": False,
            "message": "No hotkey event received within timeout",
            "delivered_count": self._delivered_count(),
            "active_provider": status.active_provider,
            "capture_healthy": status.capture_healthy,
            "hotkey_status": status.hotkey_status,
        }

    def open_settings(self, target: Literal["input_monitoring", "accessibility", "microphone"]) -> None:
        if target == "input_monitoring":
            open_input_monitoring_settings()
        elif target == "accessibility":
            open_accessibility_settings()
        else:
            open_microphone_settings()

    @staticmethod
    def _read_launcher_status() -> str:
        status_file = Path.home() / ".dictare" / "hotkey_status"
        try:
            return status_file.read_text().strip()
        except FileNotFoundError:
            return "unknown"

    @staticmethod
    def _delivered_count() -> int:
        runtime = read_runtime_status() or {}
        val = runtime.get("delivered_count", 0)
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

def status_to_dict(status: DoctorStatus) -> dict:
    return {
        "accessibility": status.accessibility,
        "microphone": status.microphone,
        "input_monitoring": status.input_monitoring,
        "hotkey_status": status.hotkey_status,
        "capture_healthy": status.capture_healthy,
        "active_provider": status.active_provider,
    }
