"""Status report assembly for the /openvip/status endpoint.

Builds the full OpenVIP status dict by reading DictareEngine state.
Extracted from DictareEngine — pure read-side assembly, no engine mutation
except the lazy engines-availability cache.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from dictare import __version__

if TYPE_CHECKING:
    from dictare.core.engine import DictareEngine

_EXIT_PHRASES: list[str] = [
    "Your fingers are getting jealous.",
    "The keyboard is overrated.",
    "Voice: 1, Keyboard: 0.",
    "Dictation: because typing is so last century.",
    "Your hands thank you.",
    "Talk is cheap — unless it's voice-to-code.",
    "Words spoken, keystrokes avoided.",
    "Efficiency is just another word for talking to your computer.",
    "Your vocal cords are your best developer tool.",
    "Less typing, more thinking.",
]


def build_status(engine: DictareEngine) -> dict:
    """Build engine status dict.

    Returns OpenVIP protocol-level fields at the top level,
    with implementation-specific details in the 'platform' object.
    """
    from dictare.core.fsm import AppState

    # Map engine state to string
    state_map = {
        AppState.OFF: "off",
        AppState.LISTENING: "listening",
        AppState.RECORDING: "recording",
        AppState.TRANSCRIBING: "transcribing",
        AppState.INJECTING: "transcribing",
        AppState.PLAYING: "playing",
    }
    stt_state = state_map.get(engine.state, "off")

    # Voice muted overrides the displayed state
    if engine._voice_muted and stt_state == "listening":
        stt_state = "muted"

    uptime = (
        time.time() - engine._stats.start_time
        if engine._stats.start_time
        else 0
    )

    stt_active = stt_state not in ("off",)

    return {
        # OpenVIP protocol-level fields
        "openvip": "1.0",
        "stt": {"enabled": True, "active": stt_active},
        "tts": {"enabled": engine._tts_mgr.available},
        "connected_agents": engine.visible_agents,
        # Implementation-specific details (StatusPanel)
        "platform": {
            "name": "Dictare",
            "version": __version__,
            "mode": "agents" if engine.agent_mode else "keyboard",
            "state": stt_state,
            "uptime_seconds": uptime,
            "stt": {
                "model_name": engine.config.stt.model,
                "device": getattr(engine._stt, "_device", engine.config.stt.advanced.device),
                "last_text": engine._last_text,
            },
            "output": {
                "mode": "agents" if engine.agent_mode else "keyboard",
                "current_agent": engine.visible_current_agent,
                "available_agents": engine.visible_agents,
            },
            "hotkey": {
                "key": engine.config.hotkey.key,
                "bound": hotkey_active(engine),
                "status": hotkey_status_raw(engine),
            },
            "tts": {
                "engine": engine.config.tts.engine,
                "language": engine.config.tts.language,
                "available": engine._tts_mgr.available,
                "error": engine._tts_mgr.error or None,
            },
            "audio_devices": {
                "input": engine.config.audio.input_device or "(default)",
                "output": engine.config.audio.output_device or "(default)",
            },
            "audio_in_use": engine._audio_manager.get_actual_devices() if engine._audio_manager else {"input": None, "output": None},
            "audio_devices_available": audio_devices(),
            "permissions": permissions(),
            "loading": {
                "active": engine._loading,
                "models": [
                    {
                        "name": m["name"],
                        "status": m["status"],
                        "elapsed": round(time.time() - m["start_time"], 1) if m["status"] == "loading" else m["elapsed"],
                        "estimated": m["estimated"],
                    }
                    for m in engine._loading_models
                ],
            },
            "engines": engines_cache(engine),
            "stats": session_stats(engine),
        },
    }


def audio_devices() -> dict:
    """Return current audio device lists for status response."""
    from dictare.audio.capture import AudioCapture

    try:
        return {
            "input": AudioCapture.list_devices(),
            "output": AudioCapture.list_output_devices(),
            "default_input": AudioCapture.get_default_device(),
            "default_output": AudioCapture.get_default_output_device(),
        }
    except Exception:
        return {"input": [], "output": [], "default_input": None, "default_output": None}


def session_stats(engine: DictareEngine) -> dict:
    """Return today's cumulative stats for the status response.

    Combines the in-memory session counters (since this engine start)
    with the persisted today_baseline (previous engine runs today),
    so the dashboard always shows the full daily total.
    """
    b = engine._today_baseline
    count = engine._stats.count + b.get("transcriptions", 0)
    words = engine._stats.words + b.get("words", 0)
    chars = engine._stats.chars + b.get("chars", 0)
    audio = engine._stats.audio_seconds + b.get("audio_seconds", 0.0)
    phrase = _EXIT_PHRASES[count % len(_EXIT_PHRASES)] if count > 0 else ""
    return {
        "transcriptions": count,
        "words": words,
        "chars": chars,
        "audio_seconds": round(audio, 1),
        "transcription_seconds": round(engine._stats.transcription_seconds + b.get("transcription_seconds", 0.0), 1),
        "injection_seconds": round(engine._stats.injection_seconds + b.get("injection_seconds", 0.0), 1),
        "phrase": phrase,
    }


def engines_cache(engine: DictareEngine) -> dict:
    """Return cached engine availability (computed once, lazy)."""
    if engine._engines_cache is None:
        from dictare.utils.platform import check_all_stt_engines, check_all_tts_engines

        engine._engines_cache = {
            "tts": check_all_tts_engines(engine.config.tts.engine),
            "stt": check_all_stt_engines(engine.config.stt.model),
        }
    return engine._engines_cache


def hotkey_active(engine: DictareEngine) -> bool:
    """Return True if the hotkey is actually functional.

    On Linux / terminal mode: Python directly binds the hotkey listener.
    On macOS daemon mode: serve writes ~/.dictare/hotkey_runtime_status
    with capture health derived from active providers (ipc/pynput/signal).
    If runtime status is unavailable, we fall back to launcher hotkey_status.
    """
    import sys

    if engine._hotkey is not None:
        return True
    if sys.platform == "darwin":
        from dictare.hotkey.runtime_status import read_runtime_status

        runtime = read_runtime_status()
        if runtime is not None:
            return bool(runtime.get("capture_healthy", False))

        from pathlib import Path
        status_file = Path.home() / ".dictare" / "hotkey_status"
        try:
            return status_file.read_text().strip() in ("active", "confirmed")
        except FileNotFoundError:
            pass
    return False


def hotkey_status_raw(engine: DictareEngine) -> str:
    """Return the raw hotkey_status string for diagnostics."""
    import sys

    if engine._hotkey is not None:
        return "bound"
    if sys.platform == "darwin":
        from dictare.hotkey.runtime_status import read_runtime_status

        runtime = read_runtime_status()
        if runtime is not None:
            status = str(runtime.get("status", "unknown"))
        else:
            from pathlib import Path
            status_file = Path.home() / ".dictare" / "hotkey_status"
            try:
                status = status_file.read_text().strip()
            except FileNotFoundError:
                status = "unknown"

        # If tap is created ("active") but the launcher binary hasn't
        # changed since last confirmation, TCC trust is still valid.
        if status == "active" and engine._hotkey_pre_confirmed:
            return "confirmed"
        return status
    return "unknown"


def check_launcher_hash() -> bool:
    """Check if launcher binary matches the previously confirmed hash."""
    import sys
    if sys.platform != "darwin":
        return False
    try:
        from dictare.hotkey.ipc import check_confirmed_launcher_hash
        return check_confirmed_launcher_hash()
    except Exception:
        return False


def permissions() -> dict:
    """Check platform permissions (Accessibility + Microphone)."""
    import sys

    if sys.platform != "darwin":
        return {"accessibility": True, "microphone": True}

    from dictare.platform.permissions import (
        ACCESSIBILITY_SETTINGS_URL,
        MICROPHONE_SETTINGS_URL,
        get_permissions,
    )

    perms = get_permissions()
    return {
        **perms,
        "accessibility_url": ACCESSIBILITY_SETTINGS_URL,
        "microphone_url": MICROPHONE_SETTINGS_URL,
    }
