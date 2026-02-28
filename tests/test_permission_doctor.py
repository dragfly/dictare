from __future__ import annotations

from dictare.platform.permission_doctor import PermissionDoctor, status_to_dict


def test_doctor_diagnosis_missing_input_monitoring(monkeypatch) -> None:
    monkeypatch.setattr(
        "dictare.platform.permissions.get_permissions",
        lambda: {"accessibility": True, "microphone": True, "input_monitoring": False},
    )
    monkeypatch.setattr(
        "dictare.platform.permission_doctor.read_runtime_status",
        lambda: {"status": "failed", "capture_healthy": False, "active_provider": "none"},
    )

    doctor = PermissionDoctor()
    status = doctor.get_status()
    diagnosis = doctor.diagnose(status)

    assert diagnosis.code == "missing_input_monitoring"
    assert diagnosis.recommended_target == "input_monitoring"


def test_doctor_diagnosis_granted_but_no_delivery(monkeypatch) -> None:
    monkeypatch.setattr(
        "dictare.platform.permissions.get_permissions",
        lambda: {"accessibility": True, "microphone": True, "input_monitoring": True},
    )
    monkeypatch.setattr(
        "dictare.platform.permission_doctor.read_runtime_status",
        lambda: {"status": "active", "capture_healthy": False, "active_provider": "none"},
    )

    doctor = PermissionDoctor()
    status = doctor.get_status()
    diagnosis = doctor.diagnose(status)

    assert diagnosis.code == "granted_but_no_delivery"
    assert diagnosis.recommended_target == "input_monitoring"


def test_status_to_dict_includes_diagnosis(monkeypatch) -> None:
    monkeypatch.setattr(
        "dictare.platform.permissions.get_permissions",
        lambda: {"accessibility": True, "microphone": True, "input_monitoring": True},
    )
    monkeypatch.setattr(
        "dictare.platform.permission_doctor.read_runtime_status",
        lambda: {"status": "confirmed", "capture_healthy": True, "active_provider": "ipc"},
    )

    doctor = PermissionDoctor()
    status = doctor.get_status()
    data = status_to_dict(status)

    assert data["diagnosis"]["code"] == "ok"
    assert data["diagnosis"]["recommended_target"] is None
