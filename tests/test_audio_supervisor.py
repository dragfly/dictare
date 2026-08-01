"""Concurrency and poison-state tests for the single-owner audio executor."""

from __future__ import annotations

import threading

import pytest

from dictare.audio.capture import PortAudioCallTimeoutError
from dictare.audio.supervisor import AudioControl, AudioControlPoisonedError
from dictare.config import AudioConfig
from dictare.core.audio_manager import AudioManager


def test_all_lifecycle_actions_run_serially_on_one_owner() -> None:
    control = AudioControl()
    thread_ids: list[int] = []
    active = 0
    max_active = 0
    state_lock = threading.Lock()

    def action() -> None:
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
        thread_ids.append(threading.get_ident())
        with state_lock:
            active -= 1

    callers = [
        threading.Thread(target=lambda: control.execute("lifecycle", action))
        for _ in range(12)
    ]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join()

    assert max_active == 1
    assert set(thread_ids) == {control.owner_thread_id}
    control.shutdown()


def test_duplicate_events_coalesce_to_one_queued_follow_up() -> None:
    control = AudioControl()
    first_started = threading.Event()
    release_first = threading.Event()
    calls: list[int] = []

    def recovery() -> None:
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            first_started.set()
            assert release_first.wait(timeout=2.0)

    assert control.request("device_change", recovery, coalesce_key="device")
    assert first_started.wait(timeout=2.0)

    accepted = [
        control.request("device_change", recovery, coalesce_key="device")
        for _ in range(20)
    ]
    assert accepted.count(True) == 1
    release_first.set()
    control.barrier()

    assert calls == [1, 2]
    control.shutdown()


def test_native_timeout_poisons_process_and_rejects_cleanup() -> None:
    poisoned: list[str] = []
    cleanup_calls: list[str] = []
    control = AudioControl(on_poisoned=poisoned.append)

    def timeout() -> None:
        raise PortAudioCallTimeoutError("PortAudio open timed out after 5.0s")

    with pytest.raises(AudioControlPoisonedError, match="open_input"):
        control.execute("open_input", timeout)

    with pytest.raises(AudioControlPoisonedError):
        control.execute("cleanup", lambda: cleanup_calls.append("unsafe"))

    assert control.poisoned
    assert len(poisoned) == 1
    assert cleanup_calls == []
    control.shutdown()


def test_regular_audio_error_does_not_poison_owner() -> None:
    control = AudioControl()

    with pytest.raises(ValueError, match="device missing"):
        control.execute("open_input", lambda: (_ for _ in ()).throw(ValueError("device missing")))

    assert not control.poisoned
    assert control.execute("retry", lambda: 42) == 42
    control.shutdown()


def test_manager_skips_native_cleanup_after_reinit_timeout() -> None:
    poisoned: list[str] = []
    manager = AudioManager(config=AudioConfig(), on_poisoned=poisoned.append)
    manager._audio = type(
        "Capture",
        (),
        {"emergency_abort": lambda self: None},
    )()

    def timeout(*_args: object, **_kwargs: object) -> None:
        raise PortAudioCallTimeoutError("PortAudio reinit timed out after 3.0s")

    with (
        pytest.MonkeyPatch.context() as monkeypatch,
        pytest.raises(AudioControlPoisonedError),
    ):
        monkeypatch.setattr("dictare.audio.beep.stop_portaudio_output", lambda: None)
        monkeypatch.setattr(manager, "_reinit_portaudio", timeout)
        manager.reset_audio_input()

    cleanup_called: list[str] = []
    manager._stop_streaming_owned = lambda: cleanup_called.append("unsafe")  # type: ignore[method-assign]
    manager.close()

    assert manager.audio_control_poisoned
    assert len(poisoned) == 1
    assert cleanup_called == []


def test_feedback_playback_is_suppressed_while_system_is_asleep() -> None:
    manager = AudioManager(config=AudioConfig())
    manager._sleeping = True
    playback_calls: list[str] = []

    manager._execute_audio_lifecycle(
        "play_output",
        lambda: playback_calls.append("unsafe"),
    )

    assert playback_calls == []
    manager._control.shutdown()
