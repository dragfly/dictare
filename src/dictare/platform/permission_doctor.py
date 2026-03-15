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

@dataclass
class DoctorDiagnosis:
    code: str
    summary: str
    steps: list[str]
    recommended_target: Literal["input_monitoring", "accessibility", "microphone"] | None = None

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

    def diagnose(self, status: DoctorStatus | None = None) -> DoctorDiagnosis:
        """Return deterministic diagnosis + guided manual steps."""
        status = status or self.get_status()

        if not status.microphone:
            return DoctorDiagnosis(
                code="missing_microphone",
                summary="Microphone permission is not granted.",
                recommended_target="microphone",
                steps=[
                    "Open Microphone settings and enable Dictare.",
                    "Click Restart Dictare below and test speech input.",
                ],
            )

        if not status.input_monitoring:
            return DoctorDiagnosis(
                code="missing_input_monitoring",
                summary="Input Monitoring permission is not granted.",
                recommended_target="input_monitoring",
                steps=[
                    "Open Input Monitoring settings and enable Dictare.",
                    "Click Restart Dictare below after granting permission.",
                    "Run Probe Hotkey and press Right Command.",
                ],
            )

        if status.hotkey_status == "failed":
            return DoctorDiagnosis(
                code="tap_creation_failed",
                summary="macOS denied event-tap creation in the launcher process.",
                recommended_target="input_monitoring",
                steps=[
                    "Open Input Monitoring settings and re-toggle Dictare.",
                    "Click Restart Dictare below to recreate the event tap.",
                    "Run Probe Hotkey and press Right Command.",
                ],
            )

        if status.capture_healthy:
            return DoctorDiagnosis(
                code="ok",
                summary="Permissions and runtime hotkey capture look healthy.",
                steps=[
                    "No permission action required.",
                ],
            )

        if status.hotkey_status in ("active", "confirmed"):
            return DoctorDiagnosis(
                code="granted_but_no_delivery",
                summary="Permissions appear granted, but no hotkey event reached the engine.",
                recommended_target="input_monitoring",
                steps=[
                    "Run Probe Hotkey and press Right Command multiple times.",
                    "If probe still fails, toggle Dictare off/on in Input Monitoring.",
                    "Click Restart Dictare below, then probe again.",
                    "If still failing, remove Dictare from Input Monitoring and add it again via relaunch.",
                ],
            )

        if not status.accessibility:
            return DoctorDiagnosis(
                code="accessibility_unconfirmed",
                summary="Accessibility appears not granted, but this does not explain the hotkey capture failure.",
                recommended_target="accessibility",
                steps=[
                    "If you use keyboard output, open Accessibility and enable Dictare.",
                    "For hotkey issues, continue focusing on Input Monitoring + Probe Hotkey.",
                ],
            )

        return DoctorDiagnosis(
            code="unknown_state",
            summary="Hotkey runtime state is unknown.",
            recommended_target="input_monitoring",
            steps=[
                "Open Input Monitoring settings and verify Dictare is enabled.",
                "Click Restart Dictare below, then run Probe Hotkey.",
            ],
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
                diagnosis = self.diagnose(status)
                return {
                    "ok": True,
                    "message": "Hotkey event received",
                    "delivered_count": now_count,
                    "active_provider": status.active_provider,
                    "capture_healthy": status.capture_healthy,
                    "hotkey_status": status.hotkey_status,
                    "diagnosis": diagnosis_to_dict(diagnosis),
                }
            time.sleep(0.1)

        status = self.get_status()
        diagnosis = self.diagnose(status)
        return {
            "ok": False,
            "message": "No hotkey event received within timeout",
            "delivered_count": self._delivered_count(),
            "active_provider": status.active_provider,
            "capture_healthy": status.capture_healthy,
            "hotkey_status": status.hotkey_status,
            "diagnosis": diagnosis_to_dict(diagnosis),
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
    diagnosis = PermissionDoctor().diagnose(status)
    return {
        "accessibility": status.accessibility,
        "microphone": status.microphone,
        "input_monitoring": status.input_monitoring,
        "hotkey_status": status.hotkey_status,
        "capture_healthy": status.capture_healthy,
        "active_provider": status.active_provider,
        "diagnosis": diagnosis_to_dict(diagnosis),
    }

def diagnosis_to_dict(diagnosis: DoctorDiagnosis) -> dict:
    return {
        "code": diagnosis.code,
        "summary": diagnosis.summary,
        "steps": diagnosis.steps,
        "recommended_target": diagnosis.recommended_target,
    }
