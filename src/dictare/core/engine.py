"""Core engine logic without UI dependencies."""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dictare import __version__
from dictare.agent.base import Agent
from dictare.audio.feedback_policy import AudioFeedbackPolicy
from dictare.core.agent_manager import AgentManager
from dictare.core.audio_manager import AudioManager
from dictare.core.controller import StateController
from dictare.core.events import EngineEvents
from dictare.core.fsm import (
    AppState,
    DiscardCurrent,
    HotkeyPressed,
    SetListening,
    SpeechEnded,
    SpeechStarted,
    StateManager,
    SwitchAgent,
    TranscriptionCompleted,
)
from dictare.core.openvip_messages import create_message
from dictare.core.tts_manager import TTSManager
from dictare.hotkey.base import HotkeyListener
from dictare.hotkey.tap_detector import TapDetector
from dictare.pipeline import Pipeline, PipelineLoader
from dictare.stt.base import STTEngine

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dictare.config import Config
    from dictare.logging.jsonl import JSONLLogger

@dataclass(frozen=True)
class SessionStats:
    """Immutable snapshot of session statistics."""

    chars: int = 0
    words: int = 0
    count: int = 0
    audio_seconds: float = 0.0
    transcription_seconds: float = 0.0
    injection_seconds: float = 0.0
    start_time: float | None = None

@dataclass
class _MutableStats:
    """Internal mutable session counters. Use engine.stats for the public snapshot."""

    chars: int = 0
    words: int = 0
    count: int = 0
    audio_seconds: float = 0.0
    transcription_seconds: float = 0.0
    injection_seconds: float = 0.0
    start_time: float | None = None

    def snapshot(self) -> SessionStats:
        """Return a frozen SessionStats copy."""
        return SessionStats(
            chars=self.chars,
            words=self.words,
            count=self.count,
            audio_seconds=self.audio_seconds,
            transcription_seconds=self.transcription_seconds,
            injection_seconds=self.injection_seconds,
            start_time=self.start_time,
        )

class DictareEngine:
    """Core engine for voice-to-text processing.

    Coordinates audio capture, STT, hotkey detection, and text injection.
    Implements OpenVIP v1.0 protocol for voice input.

    This class contains NO UI code. Use AppController for the full application
    with audio feedback, keyboard bindings, and lifecycle management.
    """

    # Minimum recording duration in seconds
    MIN_RECORDING_DURATION = 0.3

    # Maximum time to wait for STT lock (prevents thread pile-up if STT hangs)
    STT_LOCK_TIMEOUT = 30.0

    # Double-tap detection threshold in seconds
    DOUBLE_TAP_THRESHOLD = 0.4

    # Default VAD silence duration in milliseconds
    DEFAULT_VAD_SILENCE_MS = 1200

    # The built-in keyboard agent ID
    KEYBOARD_AGENT_ID = "__keyboard__"

    # The TTS worker agent ID
    TTS_AGENT_ID = "__tts__"

    @property
    def agent_mode(self) -> bool:
        """True when outputting to agents, False when keyboard."""
        return self._agent_mgr.agent_mode

    def __init__(
        self,
        config: Config,
        events: EngineEvents | None = None,
        logger: JSONLLogger | None = None,
        hotkey_enabled: bool = True,
    ) -> None:
        """Initialize the engine.

        Args:
            config: Application configuration.
            events: Optional event handler for UI callbacks.
            logger: Optional JSONL logger for structured logging.
            hotkey_enabled: Enable hotkey listener. Set False for daemon mode
                           (macOS requires main thread for hotkey events).
        """
        self._hotkey_enabled = hotkey_enabled
        self.config = config
        self._events = events

        # Session stats (single mutable container)
        self._stats = _MutableStats()

        # Today's persisted baseline (loaded once at startup).
        # Allows _get_session_stats() to return today's full total
        # even across engine restarts within the same day.
        from dictare.utils.stats import get_today_baseline
        self._today_baseline: dict = get_today_baseline()

        # Lock for STT engine (MLX is not thread-safe)
        self._stt_lock = threading.Lock()

        # Read settings from config
        self.vad_silence_ms = config.audio.silence_ms

        # Agent manager — owns all agent state (registry, switching, output mode)
        initial_agent_id: str | None = (
            None if config.output.mode == "agents" else self.KEYBOARD_AGENT_ID
        )
        self._agent_mgr = AgentManager(initial_agent_id=initial_agent_id)
        self._agent_mgr._on_notify = self._notify_status
        self._agent_mgr._on_agent_change = lambda aid, idx: self._emit(
            "on_agent_change", aid, idx
        )
        self._agent_mgr._on_speak = lambda text: self.speak_text(text)

        # Audio feedback policy — decides whether focus-gated sounds play
        self._feedback_policy = AudioFeedbackPolicy()

        # State machine handles all state (OFF/LISTENING/RECORDING/etc)
        self._state_manager = StateManager(initial_state=AppState.OFF)

        # Event queue controller - ONLY this component modifies state
        self._controller = StateController(
            self._state_manager,
            on_state_change=self._handle_state_change,
            on_agent_change=lambda name, idx: self._emit("on_agent_change", name, idx),
        )
        self._controller.set_engine(self)

        self._running = False
        self._injection_lock = threading.Lock()  # Lock for text injection
        self._logger = logger

        # Pipelines for message processing
        self._pipeline = self._create_pipeline()
        self._executor_pipeline = self._create_executor_pipeline()
        self._input_manager: Any = None  # InputManager for keyboard/device inputs
        self._keyboard_agent: Any = None  # Special built-in agent for keyboard mode

        # Pending submit — set by double-tap during recording/transcription.
        # Consumed by _inject_text to attach submit to the next transcription.
        self._submit_pending = False

        # Voice muted flag — when True, MuteFilter discards all text
        # except listen triggers. Engine stays in LISTENING (VAD+STT active).
        self._voice_muted = False

        # Guard against concurrent audio reconnect attempts
        self._reconnecting = threading.Lock()

        # Tap detection (isolated state machine)
        # Single tap: toggle mute on/off
        # Double tap: submit (inject Enter into active window)
        self._tap_detector = TapDetector(
            threshold=self.DOUBLE_TAP_THRESHOLD,
            on_single_tap=lambda: self._controller.send(HotkeyPressed(source="hotkey")),
            on_double_tap=self._submit_action,
        )

        # Initialize components
        self._audio_manager: AudioManager | None = None
        self._stt: STTEngine | None = None
        self._hotkey: HotkeyListener | None = None
        # Pre-confirmed: launcher binary matches last confirmed hash (TCC still valid)
        self._hotkey_pre_confirmed = self._check_launcher_hash()
        # Status change callback — registered by AppController to push SSE updates.
        # Engine calls this on every status-relevant change (state, agents, mode).
        self._status_change_callback: Callable[[], None] | None = None

        # Loading progress tracking (for /status endpoint)
        self._loading = False
        self._loading_models: list[dict[str, Any]] = []
        # TTS manager — owns engine loading, worker subprocess, speech, mic-pausing
        self._tts_mgr = TTSManager(config, controller=self._controller)
        # Watchdog cancel event — allows tests to prevent os._exit()
        self._exit_watchdog_cancel = threading.Event()

        # Last transcribed text (for /status endpoint)
        self._last_text = ""

        # Cached engine availability (computed once at startup — doesn't change at runtime)
        self._engines_cache: dict | None = None

        # Note: No more _injector - each Agent handles its own transport

    def _handle_state_change(self, old: Any, new: Any, trigger: str) -> None:
        """Handle state change: emit event and notify status subscribers."""
        self._emit("on_state_change", old, new, trigger)
        self._notify_status()

    def _emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Emit event to handler if registered.

        Args:
            event: Event method name (e.g., "on_state_change").
            *args: Positional arguments for the event handler.
            **kwargs: Keyword arguments for the event handler.
        """
        if self._events and hasattr(self._events, event):
            handler = getattr(self._events, event)
            if callable(handler):
                try:
                    handler(*args, **kwargs)
                except Exception:
                    logger.exception("Error in event handler %s", event)

    def _notify_status(self) -> None:
        """Notify status change via registered callback."""
        self._check_grace_period()
        if self._status_change_callback is not None:
            self._status_change_callback()
        self._save_state()

    def _check_grace_period(self) -> None:
        """Assign first available agent once the preferred-agent grace period expires."""
        self._agent_mgr.check_grace_period()

    def _save_state(self) -> None:
        """Save current state to session-state.json.  Skipped during shutdown."""
        if not self._running:
            return
        from dictare.utils.state import save_state

        save_state(
            active_agent=self._agent_mgr.current_agent,
            listening=self.is_listening,
            focused_agent=self._feedback_policy.focused_agent,
            voice_muted=self._voice_muted,
        )

    def save_session_before_shutdown(self) -> None:
        """Save session state before SIGTERM / engine.shutdown / engine.restart."""
        from dictare.utils.state import save_state

        save_state(
            active_agent=self._agent_mgr.current_agent,
            listening=self.is_listening,
            focused_agent=self._feedback_policy.focused_agent,
            voice_muted=self._voice_muted,
        )
        logger.info(
            "session_saved: agent=%r, mode=%s, listening=%r",
            self._agent_mgr.current_agent,
            "agents" if self.agent_mode else "keyboard",
            self.is_listening,
        )

    def _restore_state(self, start_listening: bool) -> bool:
        """Restore session state, overriding config defaults.

        Returns the (possibly updated) start_listening value.

        Logic:
          1. Config already set _current_agent_id and start_listening.
          2. If a fresh session exists, override with saved values.
          3. If session is missing/expired/corrupt → config defaults stand.
        """
        from dictare.utils.state import load_state

        saved = load_state()
        if saved is None:
            logger.info("restore_state: no fresh session, using config defaults")
            return start_listening

        saved_agent = saved.get("active_agent")
        saved_listening = saved.get("listening", False)
        saved_focus = saved.get("focused_agent")
        saved_muted = saved.get("voice_muted", False)

        logger.info("restore_state: fresh session → agent=%r, listening=%r, focused=%r, muted=%r", saved_agent, saved_listening, saved_focus, saved_muted)

        self._agent_mgr.restore_session(saved_agent)

        if saved_focus:
            self._feedback_policy.set_focus(saved_focus, True)

        self._voice_muted = saved_muted

        return saved_listening

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def state(self) -> AppState:
        """Get current application state."""
        return self._state_manager.state

    @property
    def is_listening(self) -> bool:
        """Check if in LISTENING state (mic active, waiting for speech)."""
        return self._state_manager.is_listening

    @property
    def is_off(self) -> bool:
        """Check if in OFF state (mic disabled)."""
        return self._state_manager.is_off

    # Agent IDs reserved for internal use — hidden from API, rejected by HTTP
    RESERVED_AGENT_IDS = AgentManager.RESERVED_AGENT_IDS

    @property
    def agents(self) -> list[str]:
        """Get list of ALL registered agent IDs (including internal)."""
        return self._agent_mgr.agents

    @property
    def visible_agents(self) -> list[str]:
        """Get list of user-visible agent IDs (excludes internal agents)."""
        return self._agent_mgr.visible_agents

    @property
    def current_agent(self) -> str | None:
        """Get the ID of the current agent, or None if no agents."""
        return self._agent_mgr.current_agent

    @property
    def visible_current_agent(self) -> str | None:
        """Get current agent ID, or None if it's an internal agent."""
        return self._agent_mgr.visible_current_agent

    @property
    def current_agent_index(self) -> int:
        """Get the index of the current agent (0-based)."""
        return self._agent_mgr.current_agent_index

    def _get_current_agent(self) -> Agent | None:
        """Get the current Agent instance."""
        return self._agent_mgr.get_current()

    # -------------------------------------------------------------------------
    # Session Stats
    # -------------------------------------------------------------------------

    @property
    def stats(self) -> SessionStats:
        """Immutable snapshot of current session statistics."""
        return self._stats.snapshot()

    # -------------------------------------------------------------------------
    # Factory Methods
    # -------------------------------------------------------------------------

    def _create_stt_engine(
        self, model_size: str | None = None, *, headless: bool = False
    ) -> STTEngine:
        """Create and load STT engine.

        Args:
            model_size: Model size to load. If None, uses config.stt.model.
            headless: If True, skip all console output (for Engine/daemon mode).
        """
        from dictare.stt.parakeet import is_parakeet_model
        from dictare.utils.hardware import is_mlx_available

        target_model = model_size or self.config.stt.model
        engine: STTEngine
        if is_parakeet_model(target_model):
            from dictare.stt.parakeet import ParakeetEngine
            engine = ParakeetEngine()
        elif self.config.stt.hw_accel and is_mlx_available():
            from dictare.stt.mlx_whisper import MLXWhisperEngine
            engine = MLXWhisperEngine()
        else:
            from dictare.stt.faster_whisper import FasterWhisperEngine
            engine = FasterWhisperEngine()

        engine.load_model(
            model_size or self.config.stt.model,
            device=self.config.stt.advanced.device,
            compute_type=self.config.stt.advanced.compute_type,
            console=None,  # No console in engine
            verbose=self.config.verbose,
            headless=headless,
        )

        return engine

    def _create_hotkey_listener(self) -> HotkeyListener:
        """Create hotkey listener with smart fallback."""
        errors: list[str] = []

        # Try evdev first on Linux
        if sys.platform == "linux":
            try:
                from dictare.hotkey.evdev_listener import EvdevHotkeyListener

                # Get target device from config (if user specified one)
                target_device = self.config.hotkey.device or None

                modifier = self.config.hotkey.mode_switch_modifier
                evdev_listener: HotkeyListener = EvdevHotkeyListener(
                    self.config.hotkey.key,
                    target_device=target_device,
                    mode_switch_modifier=modifier,
                )

                # Check if key is available, suggest fallback if not
                if not evdev_listener.is_key_available():
                    fallback = EvdevHotkeyListener.suggest_fallback_key()
                    if fallback and fallback != self.config.hotkey.key:
                        evdev_listener = EvdevHotkeyListener(
                            fallback,
                            target_device=target_device,
                            mode_switch_modifier=modifier,
                        )

                return evdev_listener
            except ImportError:
                errors.append("evdev not installed (pip install evdev)")
            except Exception as e:
                errors.append(f"evdev error: {e}")

        # Fallback to pynput (macOS and X11)
        try:
            from dictare.hotkey.pynput_listener import PynputHotkeyListener

            pynput_listener: HotkeyListener = PynputHotkeyListener(self.config.hotkey.key)
            if pynput_listener.is_key_available():
                return pynput_listener
            else:
                errors.append(f"pynput: key {self.config.hotkey.key} not supported")
        except ImportError:
            errors.append("pynput not installed (pip install pynput)")
        except Exception as e:
            errors.append(f"pynput error: {e}")

        # No hotkey backend available
        error_details = "\n  - ".join(errors)
        raise RuntimeError(
            f"No hotkey backend available.\n"
            f"Tried:\n  - {error_details}\n\n"
            f"Install evdev (Linux): pip install evdev\n"
            f"Install pynput (macOS/X11): pip install pynput"
        )

    def _get_hotwords(self) -> str | None:
        """Build hotwords string from config and pipeline trigger words."""
        if self.config.stt.advanced.hotwords:
            return self.config.stt.advanced.hotwords
        # Auto-populate from pipeline trigger words
        if self._pipeline:
            words = self._collect_pipeline_trigger_words()
            if words:
                return ", ".join(words)
        return None

    def _collect_pipeline_trigger_words(self) -> set[str]:
        """Extract unique trigger words from all pipeline filters."""
        from dictare.pipeline.filters.agent_filter import AgentFilter
        from dictare.pipeline.filters.input_filter import InputFilter
        from dictare.pipeline.filters.mute_filter import MuteFilter

        words: set[str] = set()
        if self._pipeline is None:
            return words
        for step in self._pipeline._steps:
            if isinstance(step, InputFilter):
                for patterns in step.triggers.values():
                    for pattern in patterns:
                        words.update(w.rstrip(".") for w in pattern)
            elif isinstance(step, MuteFilter):
                for patterns in step.mute_triggers.values():
                    for pattern in patterns:
                        words.update(w.rstrip(".") for w in pattern)
                for patterns in step.listen_triggers.values():
                    for pattern in patterns:
                        words.update(w.rstrip(".") for w in pattern)
            elif isinstance(step, AgentFilter):
                words.update(step.triggers)
        return words

    def _create_pipeline(self) -> Pipeline | None:
        """Create message pipeline from config.

        Returns:
            Pipeline if enabled, None otherwise.
        """
        services = {
            "agent_ids": self.agents,
            "subscribe_to_events": True,
            "is_muted": lambda: self._voice_muted,
        }
        return PipelineLoader().build_filter_pipeline(
            self.config.pipeline, services,
        )

    def _create_executor_pipeline(self) -> Pipeline:
        """Create executor pipeline for acting on extension fields.

        Executors run after filters and handle side effects:
        - AgentSwitchExecutor: switches the current agent on x_agent_switch
        - MuteExecutor: mutes/unmutes voice on x_mute

        Returns:
            Pipeline with executors (always created, may be empty).
        """
        services = {
            "switch_fn": self._switch_to_agent_by_name_internal,
            "current_agent_fn": lambda: self._agent_mgr.current_agent,
            "mute_fn": self.mute,
            "unmute_fn": self.unmute,
        }
        return PipelineLoader().build_executor_pipeline(
            self.config.pipeline, services,
        )

    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------

    def set_status_change_callback(self, callback: Callable[[], None]) -> None:
        """Register callback for status change notifications.

        Called by AppController to wire Engine status changes to the
        HTTP adapter's SSE push. The callback is invoked on every
        status-relevant change (state transition, agent register/unregister,
        mode switch).
        """
        self._status_change_callback = callback

    def init_components(
        self, *, headless: bool = False, http_server: Any = None,
    ) -> None:
        """Initialize engine components (STT, VAD, audio, hotkey).

        Call this before start_runtime(). This loads models and creates
        the audio manager, but does not start listening.

        Args:
            headless: If True, skip all console output (for Engine/daemon mode).
            http_server: OpenVIPServer instance (enables TTS worker mode for
                heavy engines like outetts/piper/coqui).
        """
        from dictare.utils.hardware import is_mlx_available
        from dictare.utils.stats import get_model_load_time, save_model_load_time

        # Build model IDs for historical load time lookup
        model = self.config.stt.model
        from dictare.stt.parakeet import PARAKEET_MODELS, is_parakeet_model
        if is_parakeet_model(model):
            stt_model_id = PARAKEET_MODELS.get(model, model)
        elif self.config.stt.hw_accel and is_mlx_available():
            stt_model_id = f"mlx-community/whisper-{model}"
        else:
            stt_model_id = f"faster-whisper-{model}"
        vad_model_id = "silero-vad"

        tts_engine_name = self.config.tts.engine

        self._loading = True
        self._loading_models = [
            {"name": "stt", "status": "pending", "start_time": 0, "elapsed": 0,
             "estimated": get_model_load_time(stt_model_id) or 25},
            {"name": "vad", "status": "pending", "start_time": 0, "elapsed": 0,
             "estimated": get_model_load_time(vad_model_id) or 25},
            {"name": "tts", "status": "pending", "start_time": 0, "elapsed": 0,
             "estimated": get_model_load_time(tts_engine_name) or 1},
        ]

        # Load STT model
        logger.info("Loading STT model: %s", stt_model_id)
        self._loading_models[0]["start_time"] = time.time()
        self._loading_models[0]["status"] = "loading"
        try:
            self._stt = self._create_stt_engine(headless=headless)
        except Exception as exc:
            logger.error("STT model loading failed: %s", exc, exc_info=True)
            raise
        stt_elapsed = round(time.time() - self._loading_models[0]["start_time"], 1)
        self._loading_models[0]["elapsed"] = stt_elapsed
        self._loading_models[0]["status"] = "done"
        save_model_load_time(stt_model_id, stt_elapsed)
        logger.info("STT model loaded in %.1fs", stt_elapsed)

        # Note: Agent registration is handled externally by AgentRegistrar.
        # The registrar calls register_agent() to add agents before run().

        # Create audio manager with VAD
        logger.info("Loading VAD model: %s", vad_model_id)
        self._loading_models[1]["start_time"] = time.time()
        self._loading_models[1]["status"] = "loading"
        try:
            self._audio_manager = AudioManager(
                config=self.config.audio,
                verbose=self.config.verbose,
            )
            self._audio_manager.initialize(
                on_speech_start=self._on_vad_speech_start,
                on_speech_end=self._on_vad_speech_end,
                on_max_speech=self._on_max_speech_duration,
                on_partial_audio=None,
                headless=headless,
            )
        except Exception as exc:
            logger.error("VAD model loading failed: %s", exc, exc_info=True)
            raise
        vad_elapsed = round(time.time() - self._loading_models[1]["start_time"], 1)
        self._loading_models[1]["elapsed"] = vad_elapsed
        self._loading_models[1]["status"] = "done"
        save_model_load_time(vad_model_id, vad_elapsed)
        logger.info("VAD model loaded in %.1fs", vad_elapsed)

        # Wire device change callback — audio manager notifies engine
        self._audio_manager._on_devices_updated = self._notify_status

        # Load TTS engine (optional — engine continues if unavailable)
        self._tts_mgr.load(
            http_server=http_server,
            estimated=get_model_load_time(tts_engine_name) or 1,
        )
        self._loading_models[2] = self._tts_mgr.loading_status

        # Pre-cache mute/listen TTS phrases in background
        precache = self.config.pipeline.mute_filter.mute_phrases + self.config.pipeline.mute_filter.listen_phrases
        if precache:
            self._tts_mgr.precache_phrases(precache)

        # Create hotkey listener for toggle (if available and enabled)
        # Note: hotkey disabled in daemon mode - macOS requires main thread
        if self._hotkey_enabled:
            try:
                self._hotkey = self._create_hotkey_listener()
            except RuntimeError:
                self._hotkey = None
        else:
            self._hotkey = None

        # Set output device for beep playback
        if self.config.audio.output_device:
            from dictare.audio.beep import set_output_device
            set_output_device(self.config.audio.output_device)

    # -------------------------------------------------------------------------
    # VAD Callbacks
    # -------------------------------------------------------------------------

    def _on_max_speech_duration(self) -> None:
        """Handle max speech duration reached in VAD mode."""
        pass

    def _on_vad_speech_start(self) -> None:
        """Handle VAD speech start detection."""
        # Send event to controller - it handles the state transition
        self._controller.send(SpeechStarted(source="vad"))

        if self._logger:
            self._logger.log_vad_event("speech_start")

    def _on_vad_speech_end(self, audio_data: Any) -> None:
        """Handle VAD speech end detection."""
        # Capture agent NOW, before sending event
        # This ensures audio goes to the agent that was active when speech ended
        captured_agent = self._get_current_agent()

        if self._logger:
            sample_rate = self._audio_manager.sample_rate if self._audio_manager else self.config.audio.advanced.sample_rate
            duration_ms = len(audio_data) / sample_rate * 1000
            self._logger.log_vad_event("speech_end", duration_ms=duration_ms)

        # Send event to controller with captured agent
        self._controller.send(
            SpeechEnded(
                audio_data=audio_data,
                agent=captured_agent,
                source="vad",
            )
        )

    # -------------------------------------------------------------------------
    # Transcription
    # -------------------------------------------------------------------------

    def _transcribe_and_process(self, audio_data: Any, agent: Agent | None = None) -> None:
        """Transcribe audio and send to agent.

        Called by StateController when SpeechEnded is processed.

        Args:
            audio_data: Audio data to transcribe
            agent: Optional agent to use for injection. If None, uses current agent.
                   This allows capturing the agent at speech-end time, ensuring audio
                   goes to the correct agent even if agent switches during transcription.
        """
        # For realtime mode: clear partial text
        # Use provided agent (captured at speech-end time)
        captured_agent = agent if agent is not None else self._get_current_agent()

        def do_transcribe() -> None:
            transcribed_text = ""
            detected_language: str | None = None
            try:
                if not self._stt:
                    return

                # Track transcription time
                transcribe_start = time.time()
                task = "translate" if self.config.stt.translate else "transcribe"
                if not self._stt_lock.acquire(timeout=self.STT_LOCK_TIMEOUT):
                    logger.warning("STT lock timeout — previous transcription may be stuck")
                    return
                try:
                    stt_result = self._stt.transcribe(
                        audio_data,
                        language=self.config.stt.language,
                        hotwords=self._get_hotwords(),
                        beam_size=self.config.stt.advanced.beam_size,
                        max_repetitions=self.config.stt.advanced.max_repetitions,
                        task=task,
                    )
                finally:
                    self._stt_lock.release()
                transcribe_time = time.time() - transcribe_start

                text = stt_result.text
                detected_language = stt_result.language

                if text:
                    transcribed_text = text
                    self._last_text = text

                    # Update session stats
                    audio_duration = len(audio_data) / self.config.audio.advanced.sample_rate
                    self._stats.count += 1
                    self._stats.chars += len(text)
                    self._stats.words += len(text.split())
                    self._stats.audio_seconds += audio_duration
                    self._stats.transcription_seconds += transcribe_time

                    # Log transcription
                    if self._logger:
                        duration_ms = audio_duration * 1000
                        stt_ms = transcribe_time * 1000
                        self._logger.log_transcription(
                            text=text,
                            duration_ms=duration_ms,
                            language=self.config.stt.language,
                            stt_ms=stt_ms,
                        )

                    # Check if user has turned off listening
                    if self.is_off:
                        return

            except Exception as e:
                logger.exception("STT transcription failed")
                if self._logger:
                    self._logger.log_error(str(e), context="transcribe_and_process")
            finally:
                # Send completion event to controller (it handles state transition)
                self._controller.send(
                    TranscriptionCompleted(
                        text=transcribed_text,
                        agent=captured_agent,
                        language=detected_language if transcribed_text else None,
                        source="stt",
                    )
                )

        thread = threading.Thread(target=do_transcribe, daemon=True)
        thread.start()

    def _process_queued_audio(self) -> None:
        """Process any queued audio from speech that occurred during transcription.

        Called by StateController after transcription completes.
        """
        if not self._audio_manager:
            return

        sample_rate = self._audio_manager.sample_rate
        min_samples = int(sample_rate * self.MIN_RECORDING_DURATION)

        while self._audio_manager.has_queued_audio:
            audio_data = self._audio_manager.pop_queued_audio()
            if audio_data is None or len(audio_data) == 0:
                continue

            # Check minimum duration
            if len(audio_data) < min_samples:
                continue

            # Found valid audio - send as event (controller handles state)
            self._controller.send(
                SpeechEnded(
                    audio_data=audio_data,
                    agent=self._get_current_agent(),
                    source="queued",
                )
            )
            return

    # -------------------------------------------------------------------------
    # Text Injection
    # -------------------------------------------------------------------------

    def _inject_text(self, text: str, *, agent: Agent | None = None, language: str | None = None) -> None:
        """Inject text into the target agent.

        Uses OpenVIP message format - each agent handles its own transport:
        - KeyboardAgent: simulates keystrokes
        - SSEAgent: sends via Server-Sent Events (OpenVIP HTTP server)

        Message processing:
        1. Build initial message with auto_submit setting
        2. Apply pipeline filters (may set x_input.submit, modify text, etc.)
        3. Send processed message(s) to agent

        Args:
            text: Text to inject
            agent: Optional agent to use. If None, uses current agent.
                   Allows injection to a specific agent even if current changed.
        """
        auto_submit = self.config.output.auto_submit
        success = False
        method = "unknown"

        # Use provided agent or fall back to current
        target_agent = agent if agent is not None else self._get_current_agent()

        # Get language for pipeline filters
        if language:
            message_language = language
        elif self.config.stt.language != "auto":
            message_language = self.config.stt.language
        else:
            message_language = None

        # Consume pending double-tap submit (deferred from recording/transcribing)
        submit_from_double_tap = self._submit_pending
        if submit_from_double_tap:
            self._submit_pending = False

        # Build OpenVIP transcription message
        message = create_message(text, language=message_language)
        if auto_submit or submit_from_double_tap:
            message["x_input"] = {
                "ops": ["submit"],
                "source": "dictare/double-tap" if submit_from_double_tap else "dictare/engine",
                **({"trigger": "<double_tap>"} if submit_from_double_tap else {}),
            }
        else:
            message["x_input"] = {"ops": ["newline"], "source": "dictare/engine"}

        # Apply pipeline: filters (enrich) then executors (act)
        messages_to_send = [message]
        if self._pipeline:
            messages_to_send = self._pipeline.process(message)
        if self._executor_pipeline and messages_to_send:
            messages_to_send = self._executor_pipeline.process_many(messages_to_send)

        # Re-resolve target agent (executor may have switched it)
        if agent is None:
            target_agent = self._get_current_agent()

        # Lock to prevent concurrent injections
        with self._injection_lock:
            inject_start = time.time()

            if target_agent:
                # Send to agent - agent handles its own transport
                method = f"agent:{target_agent.id}"

                # Send all processed messages
                for msg in messages_to_send:
                    msg_text = msg.get("text", "")
                    x_input = msg.get("x_input", {})
                    has_submit = "submit" in (x_input.get("ops") or []) if isinstance(x_input, dict) else False
                    if not msg_text.strip() and not has_submit:
                        # Skip empty messages without submit flag
                        success = True  # Consider it successful, nothing to send
                        continue
                    msg_success = target_agent.send(msg)
                    if msg_success:
                        success = True

            else:
                # No agent available
                method = "none"

            inject_elapsed = time.time() - inject_start
            self._stats.injection_seconds += inject_elapsed

        # Determine final text and input info (after pipeline processing)
        first_msg = messages_to_send[0] if messages_to_send else {}
        final_text = first_msg.get("text", text)
        x_input_info = first_msg.get("x_input", {})
        pipeline_submit = "submit" in (x_input_info.get("ops") or []) if isinstance(x_input_info, dict) else False

        # Play submit sound when message is actually sent (pipeline or deferred double-tap).
        # Immediate double-tap (LISTENING state) plays in _submit_action() instead.
        if success and pipeline_submit:
            self._play_focus_gated_sound("submit")
        submit_trigger = x_input_info.get("trigger") if isinstance(x_input_info, dict) else None
        submit_confidence = x_input_info.get("confidence") if isinstance(x_input_info, dict) else None

        # Log injection
        if self._logger:
            self._logger.log_injection(
                text=final_text,
                method=method,
                success=success,
                auto_submit=auto_submit or pipeline_submit,
                enter_sent=None,  # Agents handle their own submission
                submit_trigger=submit_trigger,
                submit_confidence=submit_confidence,
                inject_ms=inject_elapsed * 1000,
            )

    # -------------------------------------------------------------------------
    # Audio Feedback
    # -------------------------------------------------------------------------

    def _play_focus_gated_sound(self, event: str) -> None:
        """Play a sound if the feedback policy allows it."""
        from dictare.audio.beep import get_sound_for_event, play_sound_file_async

        if not self._feedback_policy.should_play(
            event, self._agent_mgr.current_agent, self.config.audio,
        ):
            return
        enabled, path = get_sound_for_event(self.config.audio, event)
        if enabled:
            scfg = self.config.audio.sounds.get(event)
            vol = scfg.volume if scfg is not None else 1.0
            play_sound_file_async(path, volume=vol)

    # -------------------------------------------------------------------------
    # Hotkey Actions
    # -------------------------------------------------------------------------

    def _submit_action(self) -> None:
        """Send a submit action to the connected agent (double-tap hotkey).

        If the engine is currently recording/transcribing or the VAD
        detects active speech, defers the submit until the next
        _inject_text call attaches it to the transcribed message.

        If truly idle (LISTENING, no speech), sends an immediate empty
        submit message.
        """
        state = self._state_manager.state
        vad_speaking = (
            self._audio_manager is not None
            and self._audio_manager.is_speaking
        )

        if state in (AppState.RECORDING, AppState.TRANSCRIBING) or vad_speaking:
            self._submit_pending = True
            logger.debug(
                "submit_action: deferred (state=%s, vad=%s)",
                state.name, vad_speaking,
            )
            return

        agent = self._get_current_agent()
        if agent is None:
            logger.debug("submit_action: no agent connected, ignoring")
            return
        message = create_message("")
        message["x_input"] = {"ops": ["submit"], "trigger": "<double_tap>", "source": "dictare/double-tap"}
        agent.send(message)
        logger.debug("submit_action: submit sent to agent %s", agent.id)
        self._play_focus_gated_sound("submit")

    # -------------------------------------------------------------------------
    # State Control
    # -------------------------------------------------------------------------

    def toggle_listening(self) -> None:
        """Toggle listening on/off - sends event to controller."""
        self._controller.send(HotkeyPressed(source="api"))

    def set_listening(self, on: bool) -> None:
        """Set listening state on/off - sends event to controller."""
        self._controller.send(SetListening(on=on, source="api"))

    # -------------------------------------------------------------------------
    # Voice Mute
    # -------------------------------------------------------------------------

    def mute(self) -> None:
        """Mute voice input (idempotent).

        Engine stays in LISTENING — VAD+STT keep running so MuteFilter
        can detect the listen trigger. All other text is discarded.
        Plays a random TTS mute phrase.
        """
        if self._voice_muted:
            return
        self._voice_muted = True
        logger.info("voice_muted")

        # TTS feedback
        import random
        phrases = self.config.pipeline.mute_filter.mute_phrases
        if phrases and self._tts_mgr.available:
            phrase = random.choice(phrases)  # noqa: S311
            self._tts_mgr.speak_text(phrase)

        self._notify_status()

    def unmute(self) -> None:
        """Unmute voice input (idempotent).

        Resumes normal text flow through the pipeline.
        Plays a random TTS listen phrase.
        """
        if not self._voice_muted:
            return
        self._voice_muted = False
        logger.info("voice_unmuted")

        # TTS feedback
        import random
        phrases = self.config.pipeline.mute_filter.listen_phrases
        if phrases and self._tts_mgr.available:
            phrase = random.choice(phrases)  # noqa: S311
            self._tts_mgr.speak_text(phrase)

        self._notify_status()

    # -------------------------------------------------------------------------
    # Output Mode
    # -------------------------------------------------------------------------

    def set_output_mode(self, mode: str) -> None:
        """Switch output mode at runtime (keyboard <-> agents)."""
        self._agent_mgr.set_output_mode(mode)

    def toggle_mode(self) -> None:
        """Toggle between agent mode and keyboard mode."""
        new_mode = "keyboard" if self.agent_mode else "agents"
        self._agent_mgr.set_output_mode(new_mode)

    # -------------------------------------------------------------------------
    # Agent Control
    # -------------------------------------------------------------------------

    def register_agent(self, agent: Agent) -> bool:
        """Register an agent."""
        return self._agent_mgr.register(agent)

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent by ID."""
        self._feedback_policy.remove_agent(agent_id)
        return self._agent_mgr.unregister(agent_id)

    def set_agent_focus(self, agent_id: str, focused: bool) -> None:
        """Update focus state for an agent's terminal."""
        logger.info("Focus: agent=%s focused=%s", agent_id, focused)
        self._feedback_policy.set_focus(agent_id, focused)
        self._save_state()

        # Trigger immediate audio reconnect on focus-in if audio is dead.
        # After sleep/wake the main loop may be waiting on a retry timer —
        # this bypasses the wait so audio recovers in ~2-3s instead of 30s.
        if focused and self._audio_manager:
            reason = self._audio_manager.reconnect_reason
            if reason:
                logger.info("Focus-triggered audio reconnect (reason=%s)", reason)
                threading.Thread(
                    target=self._focus_reconnect,
                    daemon=True,
                    name="focus-reconnect",
                ).start()

    def _focus_reconnect(self) -> None:
        """Attempt audio reconnect triggered by focus-in event.

        Runs in a daemon thread so it doesn't block the HTTP handler.
        Uses self._reconnecting lock to avoid racing with the main loop.
        """
        if not self._audio_manager:
            return
        if not self._reconnecting.acquire(blocking=False):
            logger.debug("Focus-reconnect skipped: reconnect already in progress")
            return
        try:
            if self._audio_manager.reconnect(self._audio_manager._on_audio_chunk):
                logger.info("Focus-triggered audio reconnect succeeded")
            else:
                logger.warning("Focus-triggered audio reconnect failed")
        finally:
            self._reconnecting.release()

    def switch_agent(self, direction: int) -> None:
        """Switch to next/previous agent - sends event to controller."""
        self._controller.send(SwitchAgent(direction=direction, source="api"))

    def _switch_agent_internal(self, direction: int) -> None:
        """Internal: Actually switch agent. Called by controller."""
        self._agent_mgr.switch_by_direction(direction)

    def switch_to_agent_by_name(self, name: str) -> bool:
        """Switch to a specific agent by name - sends event to controller."""
        self._controller.send(SwitchAgent(agent_name=name, source="api"))
        return True  # Actual success determined asynchronously

    def _switch_to_agent_by_name_internal(self, name: str) -> bool:
        """Internal: Actually switch by name. Called by controller."""
        return self._agent_mgr.switch_by_name(name)

    def switch_to_agent_by_index(self, index: int) -> bool:
        """Switch to a specific agent by index (1-based) - sends event."""
        self._controller.send(SwitchAgent(agent_index=index, source="api"))
        return True  # Actual success determined asynchronously

    def _switch_to_agent_by_index_internal(self, index: int) -> bool:
        """Internal: Actually switch by index. Called by controller."""
        return self._agent_mgr.switch_by_index(index)

    def discard_current(self) -> None:
        """Discard current recording/transcription - sends event."""
        self._controller.send(DiscardCurrent(source="api"))

    def _discard_current_internal(self) -> None:
        """Internal: Actually discard. Called by controller."""
        if self._audio_manager:
            self._audio_manager.clear_queue()
            self._audio_manager.reset_vad()  # Use reset, not flush

    # -------------------------------------------------------------------------
    # TTS / Audio Feedback (delegated to TTSManager)
    # -------------------------------------------------------------------------

    def resend_last(self) -> bool:
        """Resend the last transcription to the current agent.

        Useful when the agent UI misses the input.  Works independently of the
        listening state — the shortcut can be pressed while speaking.

        Returns:
            True if there was text to resend, False if nothing was sent yet.
        """
        if not self._last_text:
            logger.debug("resend_last: no last text to resend")
            return False
        logger.info("resend_last: resending %r", self._last_text)
        self._inject_text(self._last_text)
        return True

    def speak_text(self, text: str) -> None:
        """Speak text using TTS (delegates to TTSManager)."""
        self._tts_mgr.speak_text(text)

    def speak_agent(self, agent_name: str) -> None:
        """Announce agent name via TTS (delegates to TTSManager)."""
        self._tts_mgr.speak_agent(agent_name)

    def reset_audio_input(self) -> None:
        """Reset audio input to current config. Called from HTTP endpoint."""
        if self._audio_manager:
            self._audio_manager.reset_audio_input()
            self._notify_status()

    def reset_audio_output(self, device: str) -> None:
        """Reset audio output device. Called from HTTP endpoint."""
        if self._audio_manager:
            self._audio_manager.reset_audio_output(device)
            self._notify_status()

    # -------------------------------------------------------------------------
    # Public Domain API (called by HTTP adapter and tests)
    # -------------------------------------------------------------------------

    def get_status(self) -> dict:
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
        stt_state = state_map.get(self.state, "off")

        # Voice muted overrides the displayed state
        if self._voice_muted and stt_state == "listening":
            stt_state = "muted"

        uptime = (
            time.time() - self._stats.start_time
            if self._stats.start_time
            else 0
        )

        stt_active = stt_state not in ("off",)

        return {
            # OpenVIP protocol-level fields
            "openvip": "1.0",
            "stt": {"enabled": True, "active": stt_active},
            "tts": {"enabled": self._tts_mgr.available},
            "connected_agents": self.visible_agents,
            # Implementation-specific details (StatusPanel)
            "platform": {
                "name": "Dictare",
                "version": __version__,
                "mode": "agents" if self.agent_mode else "keyboard",
                "state": stt_state,
                "uptime_seconds": uptime,
                "stt": {
                    "model_name": self.config.stt.model,
                    "device": getattr(self._stt, "_device", self.config.stt.advanced.device),
                    "last_text": self._last_text,
                },
                "output": {
                    "mode": "agents" if self.agent_mode else "keyboard",
                    "current_agent": self.visible_current_agent,
                    "available_agents": self.visible_agents,
                },
                "hotkey": {
                    "key": self.config.hotkey.key,
                    "bound": self._is_hotkey_active(),
                    "status": self._hotkey_status_raw(),
                },
                "tts": {
                    "engine": self.config.tts.engine,
                    "language": self.config.tts.language,
                    "available": self._tts_mgr.available,
                    "error": self._tts_mgr.error or None,
                },
                "audio_devices": {
                    "input": self.config.audio.input_device or "(default)",
                    "output": self.config.audio.output_device or "(default)",
                },
                "audio_in_use": self._audio_manager.get_actual_devices() if self._audio_manager else {"input": None, "output": None},
                "audio_devices_available": self._get_audio_devices(),
                "permissions": self._get_permissions(),
                "loading": {
                    "active": self._loading,
                    "models": [
                        {
                            "name": m["name"],
                            "status": m["status"],
                            "elapsed": round(time.time() - m["start_time"], 1) if m["status"] == "loading" else m["elapsed"],
                            "estimated": m["estimated"],
                        }
                        for m in self._loading_models
                    ],
                },
                "engines": self._get_engines_cache(),
                "stats": self._get_session_stats(),
            },
        }

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

    def _get_audio_devices(self) -> dict:
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

    def _get_session_stats(self) -> dict:
        """Return today's cumulative stats for the status response.

        Combines the in-memory session counters (since this engine start)
        with the persisted today_baseline (previous engine runs today),
        so the dashboard always shows the full daily total.
        """
        b = self._today_baseline
        count = self._stats.count + b.get("transcriptions", 0)
        words = self._stats.words + b.get("words", 0)
        chars = self._stats.chars + b.get("chars", 0)
        audio = self._stats.audio_seconds + b.get("audio_seconds", 0.0)
        phrase = self._EXIT_PHRASES[count % len(self._EXIT_PHRASES)] if count > 0 else ""
        return {
            "transcriptions": count,
            "words": words,
            "chars": chars,
            "audio_seconds": round(audio, 1),
            "transcription_seconds": round(self._stats.transcription_seconds + b.get("transcription_seconds", 0.0), 1),
            "injection_seconds": round(self._stats.injection_seconds + b.get("injection_seconds", 0.0), 1),
            "phrase": phrase,
        }

    def _get_engines_cache(self) -> dict:
        """Return cached engine availability (computed once, lazy)."""
        if self._engines_cache is None:
            from dictare.utils.platform import check_all_stt_engines, check_all_tts_engines

            self._engines_cache = {
                "tts": check_all_tts_engines(self.config.tts.engine),
                "stt": check_all_stt_engines(self.config.stt.model),
            }
        return self._engines_cache

    def _is_hotkey_active(self) -> bool:
        """Return True if the hotkey is actually functional.

        On Linux / terminal mode: Python directly binds the hotkey listener.
        On macOS daemon mode: serve writes ~/.dictare/hotkey_runtime_status
        with capture health derived from active providers (ipc/pynput/signal).
        If runtime status is unavailable, we fall back to launcher hotkey_status.
        """
        import sys

        if self._hotkey is not None:
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

    def _hotkey_status_raw(self) -> str:
        """Return the raw hotkey_status string for diagnostics."""
        import sys

        if self._hotkey is not None:
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
            if status == "active" and self._hotkey_pre_confirmed:
                return "confirmed"
            return status
        return "unknown"

    @staticmethod
    def _check_launcher_hash() -> bool:
        """Check if launcher binary matches the previously confirmed hash."""
        import sys
        if sys.platform != "darwin":
            return False
        try:
            from dictare.hotkey.ipc import check_confirmed_launcher_hash
            return check_confirmed_launcher_hash()
        except Exception:
            return False

    @staticmethod
    def _get_permissions() -> dict:
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

    def handle_speech(self, body: dict) -> dict:
        """Handle a speech (TTS) request (delegates to TTSManager)."""
        return self._tts_mgr.handle_speech(body)

    def list_voices(self) -> list[str]:
        """Return available voices (delegates to TTSManager)."""
        return self._tts_mgr.list_voices()

    def stop_speaking(self) -> bool:
        """Interrupt the currently playing audio (delegates to TTSManager)."""
        return self._tts_mgr.stop_speaking()

    def complete_tts(self, message_id: str, *, ok: bool, duration_ms: int = 0) -> None:
        """Signal that a TTS worker finished processing a message."""
        self._tts_mgr.complete_tts(message_id, ok=ok, duration_ms=duration_ms)

    def _start_exit_watchdog(self, exit_code: int, timeout: float = 6) -> None:
        """Start a watchdog that force-exits after *timeout* seconds.

        Used by engine.shutdown / engine.restart to break deadlocks.
        The watchdog honours ``_exit_watchdog_cancel`` so tests can prevent
        the ``os._exit()`` call.
        """
        import os as _os

        cancel = self._exit_watchdog_cancel

        def _watchdog() -> None:
            import time
            time.sleep(timeout)
            if cancel.is_set():
                return
            logger.warning("Graceful shutdown timed out — forcing exit")
            _os._exit(exit_code)

        threading.Thread(target=_watchdog, daemon=True, name="shutdown-watchdog").start()

    def handle_protocol_command(self, body: dict) -> dict:
        """Handle an OpenVIP protocol command.

        Protocol commands: stt.start, stt.stop, stt.toggle, engine.shutdown, engine.restart, ping.

        Args:
            body: Request body with "command" field.

        Returns:
            Response dict.
        """
        command = body.get("command", "")

        if command == "stt.start":
            self.set_listening(True)
            return {"status": "ok", "listening": True}
        elif command == "stt.stop":
            self.set_listening(False)
            return {"status": "ok", "listening": False}
        elif command == "stt.toggle":
            self.toggle_listening()
            return {"status": "ok"}
        elif command == "engine.shutdown":
            self.save_session_before_shutdown()
            self._running = False
            # Watchdog: force-exit if graceful stop() hangs (e.g. audio deadlock).
            # Exit code 1 so both Restart=always and Restart=on-failure trigger a restart.
            self._start_exit_watchdog(exit_code=1)
            return {"status": "ok"}
        elif command == "engine.restart":
            # Persist state, then exit — the service manager (Restart=always) restarts us.
            self.save_session_before_shutdown()
            self._running = False
            self._start_exit_watchdog(exit_code=0)
            return {"status": "ok"}
        elif command == "ping":
            return {"status": "ok", "pong": True}
        elif command == "hotkey.capture":
            timeout = float(body.get("timeout", 10.0))
            key = self.capture_next_hotkey(timeout=timeout)
            return {"status": "ok", "key": key}

        return {"status": "error", "error": f"Unknown protocol command: {command}"}

    def capture_next_hotkey(self, timeout: float = 10.0) -> str | None:
        """Capture the next physical key press and return its evdev name.

        Blocks until a key is pressed or timeout expires.
        Returns None if no listener is running or timed out.
        """
        if self._hotkey is None:
            return None
        return self._hotkey.capture_next_key(timeout=timeout)

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start_runtime(self, *, start_listening: bool = False) -> None:
        """Start engine runtime components.

        Call this after init_components(). Starts the controller, audio streaming,
        and optionally transitions to LISTENING state.

        Args:
            start_listening: If True, transition to LISTENING state.
                           If False (default), stay in OFF state (privacy-aware).
        """
        logger.info(
            "start_runtime: agent_mode=%r, current_agent=%r, "
            "agents=%s, hotkey=%r, start_listening=%r",
            self.agent_mode, self._agent_mgr.current_agent,
            self._agent_mgr.agents,
            self._hotkey is not None,
            start_listening,
        )

        self._running = True
        self._stats.start_time = time.time()

        # Start keyboard agent if in keyboard mode (special built-in agent)
        if self._keyboard_agent:
            self._keyboard_agent.start()

        # Start the state controller (event queue processor)
        self._controller.start()

        # Start hotkey listener (tap detector handles single/double tap)
        if self._hotkey:
            self._hotkey.start(
                on_press=self._tap_detector.on_key_down,
                on_release=self._tap_detector.on_key_up,
                on_other_key=self._tap_detector.on_other_key,
                on_combo=self.toggle_mode,
            )

        # Start audio streaming (always needed for VAD to work)
        _t0 = time.monotonic()
        if self._audio_manager:
            self._audio_manager.start_streaming(
                should_process=lambda: (
                    self._state_manager.should_process_audio
                    and (not self.agent_mode or bool(self.visible_agents))
                ),
                is_running=lambda: self._running,
            )
        _audio_ms = (time.monotonic() - _t0) * 1000
        if _audio_ms > 500:
            logger.warning("start_runtime: start_streaming took %.0fms", _audio_ms)

        if start_listening:
            old_state = self.state
            self._state_manager.transition(AppState.LISTENING)
            logger.info("start_runtime: transitioned %s → LISTENING", old_state.name)
            self._emit("on_state_change", old_state, AppState.LISTENING, "start")

        # Everything ready — clear loading state for SSE subscribers
        self._loading = False
        self._notify_status()

    def run(self) -> None:
        """Run the engine main loop (blocking).

        Call start_runtime() first. This keeps the main thread alive and
        handles audio device reconnection (callback errors, dead streams,
        zombie streams).
        """
        try:
            while self._running:
                time.sleep(0.1)
                if not self._audio_manager:
                    continue

                reason = self._audio_manager.reconnect_reason
                if reason:
                    logger.warning("Audio reconnect needed: %s", reason)
                    if not self._reconnecting.acquire(blocking=False):
                        continue  # focus-reconnect already in progress
                    try:
                        if self._audio_manager.reconnect(self._audio_manager._on_audio_chunk):
                            logger.info("Audio reconnect succeeded")
                        else:
                            logger.error("Audio reconnect failed — waiting 3s before retry")
                            _deadline = time.monotonic() + 3.0
                            while self._running and time.monotonic() < _deadline:
                                time.sleep(0.5)
                    finally:
                        self._reconnecting.release()
        except KeyboardInterrupt:
            pass

    def start(self, *, start_listening: bool = True) -> None:
        """Initialize and start the engine (convenience method).

        This is equivalent to:
            engine.init_components()
            engine.start_runtime(start_listening=start_listening)
            engine.run()

        Args:
            start_listening: If True, immediately transition to LISTENING state.
        """
        self.init_components()
        self.start_runtime(start_listening=start_listening)
        self.run()

    def stop(self) -> None:
        """Stop the engine."""
        self._running = False

        # Stop the state controller first
        self._controller.stop()

        # Force transition to OFF
        self._state_manager.transition(AppState.OFF, force=True)

        # Close audio/VAD
        if self._audio_manager:
            self._audio_manager.flush_vad()
            self._audio_manager.close()

        # Cancel any pending tap timer
        self._tap_detector.reset()

        if self._input_manager:
            self._input_manager.stop()

        # Stop keyboard agent if in keyboard mode
        if self._keyboard_agent:
            self._keyboard_agent.stop()
            self._keyboard_agent = None

        # Note: AgentRegistrar.stop() is called by the app, not here

        if self._hotkey:
            self._hotkey.stop()

        # Terminate TTS worker subprocess
        self._tts_mgr.stop()

def create_engine(
    config: Config,
    events: EngineEvents,
    *,
    logger: JSONLLogger | None = None,
    hotkey_enabled: bool = True,
) -> DictareEngine:
    """Create a DictareEngine.

    In agent mode, agents self-register via SSE connection to the HTTP server.
    In keyboard mode, a KeyboardAgent is created and managed internally.
    Mode is determined by config.output.mode and _current_agent_id.

    Args:
        config: Application configuration.
        events: Event handler callbacks.
        logger: Optional JSONL logger.
        hotkey_enabled: Enable hotkey listener. Set False for daemon mode
                       (macOS requires main thread for hotkey events).

    Returns:
        Configured DictareEngine instance.
    """
    _log = logging.getLogger(__name__)

    engine = DictareEngine(
        config=config,
        events=events,
        logger=logger,
        hotkey_enabled=hotkey_enabled,
    )

    # Always create KeyboardAgent — mode switch just changes current_agent_id
    from dictare.agent.keyboard import KeyboardAgent

    keyboard_agent = KeyboardAgent(config)
    engine._keyboard_agent = keyboard_agent
    engine.register_agent(keyboard_agent)

    _log.info(
        "create_engine done: agent_mode=%r, current_agent=%r",
        engine.agent_mode, engine.current_agent,
    )
    return engine
