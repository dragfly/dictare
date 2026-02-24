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
from dictare.core.audio_manager import AudioManager
from dictare.core.bus import bus
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
        return self._current_agent_id != self.KEYBOARD_AGENT_ID

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

        # Session stats
        self._stats_chars = 0
        self._stats_words = 0
        self._stats_audio_seconds = 0.0
        self._stats_transcription_seconds = 0.0
        self._stats_injection_seconds = 0.0
        self._stats_count = 0
        self._stats_start_time: float | None = None

        # Lock for STT engine (MLX is not thread-safe)
        self._stt_lock = threading.Lock()

        # Read settings from config
        self.vad_silence_ms = config.audio.silence_ms

        self._agents: dict[str, Agent] = {}  # ID -> Agent instance
        # Note: Agent registration is handled externally via register_agent()/
        # unregister_agent() API. The app creates the appropriate AgentRegistrar.
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

        # Agent state (must be initialized before pipeline)
        # _current_agent_id drives agent_mode property:
        #   KEYBOARD_AGENT_ID → keyboard mode, anything else → agent mode
        self._current_agent_id: str | None = (
            None if config.output.mode == "agents" else self.KEYBOARD_AGENT_ID
        )
        self._agent_order: list[str] = []  # Ordered list of agent IDs for cycling

        # Pipelines for message processing
        self._pipeline = self._create_pipeline()
        self._executor_pipeline = self._create_executor_pipeline()
        self._input_manager: Any = None  # InputManager for keyboard/device inputs
        self._keyboard_agent: Any = None  # Special built-in agent for keyboard mode
        self._last_sse_agent_id: str | None = None  # Remember last SSE agent for mode switch
        # Grace period after restart: give the preferred agent time to reconnect
        # before auto-assigning any first-come agent.  Set in _restore_state().
        self._preferred_agent_deadline: float | None = None

        # Tap detection (isolated state machine)
        # Single tap: toggle listening on/off
        # Double tap: toggle output mode (agents <-> keyboard)
        self._tap_detector = TapDetector(
            threshold=self.DOUBLE_TAP_THRESHOLD,
            on_single_tap=lambda: self._controller.send(HotkeyPressed(source="hotkey")),
            on_double_tap=lambda: self.set_output_mode(
                "keyboard" if self.agent_mode else "agents"
            ),
        )

        # Initialize components
        self._audio_manager: AudioManager | None = None
        self._stt: STTEngine | None = None
        self._hotkey: HotkeyListener | None = None
        # Status change callback — registered by AppController to push SSE updates.
        # Engine calls this on every status-relevant change (state, agents, mode).
        self._status_change_callback: Callable[[], None] | None = None

        # Loading progress tracking (for /status endpoint)
        self._loading = False
        self._loading_models: list[dict[str, Any]] = []
        # TTS engine (loaded at startup, None if unavailable)
        self._tts_engine: Any = None
        self._tts_error: str = ""
        self._tts_proxy: Any = None  # WorkerTTSEngine (set when using worker)
        self._tts_worker_process: Any = None  # subprocess.Popen for TTS worker

        # Scoped auth tokens for internal services
        import secrets
        self._auth_tokens: dict[str, str] = {
            "register_tts": secrets.token_urlsafe(32),
        }
        # Watchdog cancel event — allows tests to prevent os._exit()
        self._exit_watchdog_cancel = threading.Event()

        # Last transcribed text (for /status endpoint)
        self._last_text = ""

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
                    logger.exception(f"Error in event handler {event}")

    def _notify_status(self) -> None:
        """Notify status change via registered callback."""
        self._check_grace_period()
        if self._status_change_callback is not None:
            self._status_change_callback()
        self._save_state()

    def _check_grace_period(self) -> None:
        """Assign first available agent once the preferred-agent grace period expires."""
        import time as _time

        if self._preferred_agent_deadline is None:
            return
        if _time.monotonic() < self._preferred_agent_deadline:
            return
        # Grace period expired without the preferred agent reconnecting
        self._preferred_agent_deadline = None
        if self.agent_mode and (
            self._current_agent_id is None
            or self._current_agent_id in self.RESERVED_AGENT_IDS
        ):
            visible = self.visible_agents
            if visible:
                self._current_agent_id = visible[0]
                logger.info(
                    "grace_period_expired: preferred agent never reconnected, "
                    "activating first available agent %r",
                    visible[0],
                )

    def _save_state(self) -> None:
        """Save current state to session-state.json.  Skipped during shutdown."""
        if not self._running:
            return
        from dictare.utils.state import save_state

        save_state(active_agent=self._current_agent_id, listening=self.is_listening)

    def save_session_before_shutdown(self) -> None:
        """Save session state before SIGTERM / engine.shutdown / engine.restart."""
        from dictare.utils.state import save_state

        save_state(active_agent=self._current_agent_id, listening=self.is_listening)
        logger.info(
            "session_saved: agent=%r, mode=%s, listening=%r",
            self._current_agent_id,
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

        logger.info("restore_state: fresh session → agent=%r, listening=%r", saved_agent, saved_listening)

        # Restore agent: if it's a real agent, wait for it to reconnect
        if saved_agent and saved_agent != self.KEYBOARD_AGENT_ID:
            import time as _time

            self._current_agent_id = None  # agents mode, waiting
            self._last_sse_agent_id = saved_agent
            self._preferred_agent_deadline = _time.monotonic() + 20.0
            logger.info("restore_state: waiting for agent %r (20s grace)", saved_agent)
        elif saved_agent == self.KEYBOARD_AGENT_ID:
            self._current_agent_id = self.KEYBOARD_AGENT_ID
            logger.info("restore_state: keyboard mode")

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
    RESERVED_AGENT_IDS = frozenset({KEYBOARD_AGENT_ID, TTS_AGENT_ID})

    @property
    def agents(self) -> list[str]:
        """Get list of ALL registered agent IDs (including internal)."""
        return self._agent_order.copy()

    @property
    def visible_agents(self) -> list[str]:
        """Get list of user-visible agent IDs (excludes internal agents)."""
        return [a for a in self._agent_order if a not in self.RESERVED_AGENT_IDS]

    @property
    def current_agent(self) -> str | None:
        """Get the ID of the current agent, or None if no agents."""
        return self._current_agent_id

    @property
    def visible_current_agent(self) -> str | None:
        """Get current agent ID, or None if it's an internal agent."""
        if self._current_agent_id in self.RESERVED_AGENT_IDS:
            return None
        return self._current_agent_id

    @property
    def current_agent_index(self) -> int:
        """Get the index of the current agent (0-based)."""
        if self._current_agent_id and self._current_agent_id in self._agent_order:
            return self._agent_order.index(self._current_agent_id)
        return 0

    def _get_current_agent(self) -> Agent | None:
        """Get the current Agent instance."""
        if self._current_agent_id:
            return self._agents.get(self._current_agent_id)
        return None

    # -------------------------------------------------------------------------
    # Session Stats
    # -------------------------------------------------------------------------

    @property
    def stats(self) -> SessionStats:
        """Immutable snapshot of current session statistics."""
        return SessionStats(
            chars=self._stats_chars,
            words=self._stats_words,
            count=self._stats_count,
            audio_seconds=self._stats_audio_seconds,
            transcription_seconds=self._stats_transcription_seconds,
            injection_seconds=self._stats_injection_seconds,
            start_time=self._stats_start_time,
        )

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

                evdev_listener: HotkeyListener = EvdevHotkeyListener(
                    self.config.hotkey.key,
                    target_device=target_device,
                )

                # Check if key is available, suggest fallback if not
                if not evdev_listener.is_key_available():
                    fallback = EvdevHotkeyListener.suggest_fallback_key()
                    if fallback and fallback != self.config.hotkey.key:
                        evdev_listener = EvdevHotkeyListener(
                            fallback,
                            target_device=target_device,
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
        """Build hotwords string from config."""
        if self.config.stt.advanced.hotwords:
            return self.config.stt.advanced.hotwords
        return None

    def _create_pipeline(self) -> Pipeline | None:
        """Create message pipeline from config.

        Returns:
            Pipeline if enabled, None otherwise.
        """
        services = {"agent_ids": self.agents, "subscribe_to_events": True}
        return PipelineLoader().build_filter_pipeline(
            self.config.pipeline, services,
        )

    def _create_executor_pipeline(self) -> Pipeline:
        """Create executor pipeline for acting on extension fields.

        Executors run after filters and handle side effects:
        - AgentSwitchExecutor: switches the current agent on x_agent_switch

        Returns:
            Pipeline with executors (always created, may be empty).
        """
        services = {"switch_fn": self._switch_to_agent_by_name_internal}
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

        # Load TTS engine (optional — engine continues if unavailable)
        # Heavy engines (outetts, piper, coqui) run in a worker subprocess
        # to avoid blocking the main process with model loading.
        _worker_engines = {"outetts", "piper", "coqui"}
        use_worker = (
            tts_engine_name in _worker_engines and http_server is not None
        )

        logger.debug("Loading TTS engine: %s (worker=%s)", tts_engine_name, use_worker)
        self._loading_models[2]["start_time"] = time.time()
        self._loading_models[2]["status"] = "loading"

        if use_worker:
            try:
                self._spawn_tts_worker(http_server)
                tts_elapsed = round(time.time() - self._loading_models[2]["start_time"], 1)
                self._loading_models[2]["elapsed"] = tts_elapsed
                self._loading_models[2]["status"] = "done"
                save_model_load_time(tts_engine_name, tts_elapsed)
                logger.info("TTS worker spawned in %.1fs", tts_elapsed)
            except Exception as exc:
                tts_elapsed = round(time.time() - self._loading_models[2]["start_time"], 1)
                self._loading_models[2]["elapsed"] = tts_elapsed
                self._loading_models[2]["status"] = "error"
                self._tts_error = str(exc)
                logger.warning(
                    "TTS worker failed to start, falling back to in-process: %s", exc
                )
                # Fallback to in-process loading
                self._load_tts_in_process(tts_engine_name, save_model_load_time)
        else:
            self._load_tts_in_process(tts_engine_name, save_model_load_time)

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
    # TTS Loading Helpers
    # -------------------------------------------------------------------------

    def _load_tts_in_process(
        self, engine_name: str, save_fn: Any = None,
    ) -> None:
        """Load a TTS engine in the main process (lightweight engines)."""
        try:
            from dictare.tts import get_cached_tts_engine

            self._tts_engine = get_cached_tts_engine(self.config.tts)
            if hasattr(self._tts_engine, "_get_model_path"):
                self._tts_engine._get_model_path()
            tts_elapsed = round(time.time() - self._loading_models[2]["start_time"], 1)
            self._loading_models[2]["elapsed"] = tts_elapsed
            self._loading_models[2]["status"] = "done"
            if save_fn:
                save_fn(engine_name, tts_elapsed)
            logger.debug("TTS engine loaded in-process in %.1fs", tts_elapsed)
        except ValueError as exc:
            tts_elapsed = round(time.time() - self._loading_models[2]["start_time"], 1)
            self._loading_models[2]["elapsed"] = tts_elapsed
            self._loading_models[2]["status"] = "error"
            self._tts_error = str(exc)
            logger.warning(
                "TTS engine '%s' not available — fix: dictare dependencies resolve",
                engine_name,
            )

    def _spawn_tts_worker(self, http_server: Any) -> None:
        """Spawn a persistent TTS worker subprocess and create the proxy engine."""
        import subprocess

        from dictare.tts.proxy import WorkerTTSEngine

        token = self._auth_tokens["register_tts"]
        port = http_server.port

        cmd = [
            sys.executable, "-m", "dictare.tts.worker",
            "--url", f"http://127.0.0.1:{port}",
            "--token", token,
            "--engine", self.config.tts.engine,
            "--language", self.config.tts.language,
            "--speed", str(self.config.tts.speed),
        ]
        if self.config.tts.voice:
            cmd.extend(["--voice", self.config.tts.voice])

        logger.info("Spawning TTS worker: %s", " ".join(cmd))
        self._tts_worker_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Create proxy engine — it will wait for worker to connect
        proxy = WorkerTTSEngine(http_server)
        self._tts_proxy = proxy
        self._tts_engine = proxy

        # Wait for worker to connect, polling for early crash every 0.5s
        import time as _time

        deadline = _time.monotonic() + 120.0
        while not http_server._tts_connected_event.is_set():
            # Check if process died (fail fast instead of waiting 120s)
            if self._tts_worker_process.poll() is not None:
                stderr = self._tts_worker_process.stderr
                err_output = stderr.read().decode() if stderr else ""
                raise RuntimeError(
                    f"TTS worker exited with code {self._tts_worker_process.returncode}: "
                    f"{err_output[:500]}"
                )
            if _time.monotonic() > deadline:
                raise RuntimeError("TTS worker failed to connect within 120s")
            http_server._tts_connected_event.wait(timeout=0.5)

        logger.info("TTS worker connected")

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
                    self._stats_count += 1
                    self._stats_chars += len(text)
                    self._stats_words += len(text.split())
                    self._stats_audio_seconds += audio_duration
                    self._stats_transcription_seconds += transcribe_time

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
        1. Build initial message with auto_enter setting
        2. Apply pipeline filters (may set x_submit, modify text, etc.)
        3. Send processed message(s) to agent

        Args:
            text: Text to inject
            agent: Optional agent to use. If None, uses current agent.
                   Allows injection to a specific agent even if current changed.
        """
        auto_enter = self.config.output.auto_enter
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

        # Build OpenVIP transcription message
        message = create_message(text, language=message_language)
        if auto_enter:
            message["x_input"] = {"submit": True}
        else:
            message["x_input"] = {"newline": True}

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
                    has_submit = x_input.get("submit", False) if isinstance(x_input, dict) else False
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
            self._stats_injection_seconds += inject_elapsed

        # Determine final text and input info (after pipeline processing)
        first_msg = messages_to_send[0] if messages_to_send else {}
        final_text = first_msg.get("text", text)
        x_input_info = first_msg.get("x_input", {})
        pipeline_submit = x_input_info.get("submit", False) if isinstance(x_input_info, dict) else False
        submit_trigger = x_input_info.get("trigger") if isinstance(x_input_info, dict) else None
        submit_confidence = x_input_info.get("confidence") if isinstance(x_input_info, dict) else None

        # Log injection
        if self._logger:
            self._logger.log_injection(
                text=final_text,
                method=method,
                success=success,
                auto_enter=auto_enter or pipeline_submit,
                enter_sent=None,  # Agents handle their own submission
                submit_trigger=submit_trigger,
                submit_confidence=submit_confidence,
                inject_ms=inject_elapsed * 1000,
            )

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
    # Output Mode
    # -------------------------------------------------------------------------

    def set_output_mode(self, mode: str) -> None:
        """Switch output mode at runtime (keyboard <-> agents).

        In keyboard mode, a built-in KeyboardAgent injects keystrokes.
        In agents mode, agents self-register via SSE.
        """
        if mode not in ("keyboard", "agents"):
            return

        want_agent_mode = mode == "agents"
        if want_agent_mode == self.agent_mode:
            logger.debug("set_output_mode(%r): already in this mode, no-op", mode)
            return  # Already in this mode

        logger.info(
            "set_output_mode: %s → %s (current_agent=%r, last_sse_agent=%r)",
            "agents" if self.agent_mode else "keyboard", mode,
            self._current_agent_id, self._last_sse_agent_id,
        )

        if want_agent_mode:
            # Switch to agents: restore last SSE agent as current
            restore_id = self._last_sse_agent_id
            real_agents = self.visible_agents
            if restore_id and restore_id in self._agents:
                self._current_agent_id = restore_id
            elif real_agents:
                self._current_agent_id = real_agents[0]
            else:
                self._current_agent_id = None  # agents mode, waiting for connection
            self.speak_text("agent mode")
        else:
            # Switch to keyboard: save current agent, make __keyboard__ current
            if self._current_agent_id and self._current_agent_id != self.KEYBOARD_AGENT_ID:
                self._last_sse_agent_id = self._current_agent_id
            self._current_agent_id = self.KEYBOARD_AGENT_ID
            self.speak_text("keyboard mode")

        self._notify_status()

    def _set_current_agent(self, agent_id: str, idx: int = 0) -> None:
        """Set current agent, emit event, and push SSE status update.

        Single place for the set + emit + notify tripletta. Use this for
        intentional agent switches (voice filter, hotkey, API, mode switch).
        """
        logger.info("_set_current_agent: %s (idx=%d)", agent_id, idx)
        self._current_agent_id = agent_id
        self._emit("on_agent_change", agent_id, idx)
        self._notify_status()

    # -------------------------------------------------------------------------
    # Agent Control
    # -------------------------------------------------------------------------

    def register_agent(self, agent: Agent) -> bool:
        """Register an agent.

        This is the public API for adding agents. Can be called by any
        discovery mechanism (manual CLI args, auto-discovery watcher, etc.)

        Args:
            agent: The Agent instance to register.

        Returns:
            True if agent was added, False if already registered.
        """
        if agent.id in self._agents:
            return False

        self._agents[agent.id] = agent
        self._agent_order.append(agent.id)

        # Activate this agent if:
        # 1. It's the saved preferred agent from last session, OR
        # 2. No current agent OR current is internal (like __keyboard__) in agents mode
        if agent.id not in self.RESERVED_AGENT_IDS:
            if self._last_sse_agent_id and agent.id == self._last_sse_agent_id:
                self._current_agent_id = agent.id
                logger.info(
                    "register_agent(%s): activated (matches preferred agent from saved state)",
                    agent.id,
                )
            elif self._current_agent_id is None or (
                self.agent_mode and self._current_agent_id in self.RESERVED_AGENT_IDS
            ):
                self._current_agent_id = agent.id
                logger.info(
                    "register_agent(%s): activated as first real agent "
                    "(current_agent was %r, agent_mode=%r)",
                    agent.id, self._current_agent_id, self.agent_mode,
                )
            else:
                logger.info(
                    "register_agent(%s): registered but not activated "
                    "(current_agent=%r, preferred=%r)",
                    agent.id, self._current_agent_id, self._last_sse_agent_id,
                )
        else:
            logger.info("register_agent(%s): reserved agent registered", agent.id)

        bus.publish("agent.registered", agent_id=agent.id)
        self._notify_status()
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent by ID.

        This is the public API for removing agents.

        Args:
            agent_id: The agent identifier to remove.

        Returns:
            True if agent was removed, False if not found.
        """
        if agent_id not in self._agents:
            return False

        was_current = self._current_agent_id == agent_id

        # Remove from both dict and order list
        del self._agents[agent_id]
        self._agent_order = [a for a in self._agent_order if a != agent_id]

        # Adjust current agent if needed
        if was_current:
            visible = self.visible_agents
            if visible:
                self._set_current_agent(visible[0])
            else:
                self._current_agent_id = None


        bus.publish("agent.unregistered", agent_id=agent_id)
        self._notify_status()
        return True

    def switch_agent(self, direction: int) -> None:
        """Switch to next/previous agent - sends event to controller."""
        self._controller.send(SwitchAgent(direction=direction, source="api"))

    def _switch_agent_internal(self, direction: int) -> None:
        """Internal: Actually switch agent. Called by controller.

        Switches to the next agent in the specified direction.
        Agent liveness is verified lazily on send() - if an agent is dead,
        repeated send failures will trigger auto-deregistration.
        """
        if not self._agent_order:
            return

        # Get current index
        current_idx = 0
        if self._current_agent_id and self._current_agent_id in self._agent_order:
            current_idx = self._agent_order.index(self._current_agent_id)

        # Switch to next agent (simple circular)
        new_idx = (current_idx + direction) % len(self._agent_order)
        new_agent_id = self._agent_order[new_idx]

        if new_agent_id in self._agents:
            self._set_current_agent(new_agent_id, new_idx)

    def switch_to_agent_by_name(self, name: str) -> bool:
        """Switch to a specific agent by name - sends event to controller."""
        self._controller.send(SwitchAgent(agent_name=name, source="api"))
        return True  # Actual success determined asynchronously

    def _switch_to_agent_by_name_internal(self, name: str) -> bool:
        """Internal: Actually switch by name. Called by controller.

        Agent liveness is verified lazily on send().
        """
        if not self._agent_order:
            return False

        name_lower = name.lower()

        def try_switch(agent_id: str, idx: int) -> bool:
            """Try to switch to an agent."""
            if agent_id not in self._agents:
                return False
            self._set_current_agent(agent_id, idx)
            return True

        # Try exact match first
        for i, agent_id in enumerate(self._agent_order):
            if agent_id.lower() == name_lower:
                return try_switch(agent_id, i)

        # Try partial match
        for i, agent_id in enumerate(self._agent_order):
            if name_lower in agent_id.lower():
                return try_switch(agent_id, i)

        return False

    def switch_to_agent_by_index(self, index: int) -> bool:
        """Switch to a specific agent by index (1-based) - sends event."""
        self._controller.send(SwitchAgent(agent_index=index, source="api"))
        return True  # Actual success determined asynchronously

    def _switch_to_agent_by_index_internal(self, index: int) -> bool:
        """Internal: Actually switch by index. Called by controller.

        Agent liveness is verified lazily on send().
        """
        if not self._agent_order:
            return False

        idx = index - 1  # Convert from 1-based to 0-based
        if idx < 0 or idx >= len(self._agent_order):
            return False

        agent_id = self._agent_order[idx]
        if agent_id not in self._agents:
            return False

        self._set_current_agent(agent_id, idx)
        return True

    def discard_current(self) -> None:
        """Discard current recording/transcription - sends event."""
        self._controller.send(DiscardCurrent(source="api"))

    def _discard_current_internal(self) -> None:
        """Internal: Actually discard. Called by controller."""
        if self._audio_manager:
            self._audio_manager.clear_queue()
            self._audio_manager.reset_vad()  # Use reset, not flush

    # -------------------------------------------------------------------------
    # TTS / Audio Feedback
    # -------------------------------------------------------------------------

    def _load_tts_phrases(self) -> dict:
        """Load TTS phrases from config file or use defaults."""
        import json
        from pathlib import Path

        default_phrases = {
            "agent": "agent",
        }

        phrases_path = Path.home() / ".config" / "dictare" / "tts_phrases.json"
        if phrases_path.exists():
            try:
                with open(phrases_path) as f:
                    custom = json.load(f)
                return {**default_phrases, **custom}
            except Exception:
                pass

        return default_phrases

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
        """Speak text using the pre-loaded TTS engine, optionally pausing the mic.

        Args:
            text: Text to speak.
        """
        if self._tts_engine is None:
            logger.warning("speak_text(%r): TTS engine not loaded", text)
            return

        from dictare.audio.beep import get_sound_for_event

        enabled, _ = get_sound_for_event(self.config.audio, "agent_announce")
        if not enabled:
            return

        from dictare.audio.beep import play_audio

        tts = self._tts_engine
        logger.info("TTS: %r", text)

        def _do_tts() -> None:
            try:
                ok = tts.speak(text)
                if not ok:
                    logger.warning("TTS speak(%r) returned False", text)
            except Exception:
                logger.warning("TTS speak failed for %r", text, exc_info=True)

        pause = not self.config.audio.headphones_mode
        play_audio(_do_tts, pause_mic=pause, controller=self._controller)

    def speak_agent(self, agent_name: str) -> None:
        """Speak agent name using OS TTS.

        Announces "{agent_prefix} {agent_name}" (e.g., "agent claude").
        The prefix is configurable via ~/.config/dictare/tts_phrases.json.

        Args:
            agent_name: Name of the agent to announce.
        """
        phrases = self._load_tts_phrases()
        agent_prefix = phrases.get("agent", "agent")
        display_name = agent_name.strip("_")
        self.speak_text(f"{agent_prefix} {display_name}")

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
            AppState.OFF: "idle",
            AppState.LISTENING: "listening",
            AppState.RECORDING: "recording",
            AppState.TRANSCRIBING: "transcribing",
            AppState.INJECTING: "transcribing",
            AppState.PLAYING: "playing",
        }
        stt_state = state_map.get(self.state, "idle")

        uptime = (
            time.time() - self._stats_start_time
            if self._stats_start_time
            else 0
        )

        return {
            # OpenVIP protocol-level fields
            "protocol_version": "1.0",
            "state": stt_state,
            "connected_agents": self.visible_agents,
            "uptime_seconds": uptime,
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
                    "bound": self._hotkey is not None,
                },
                "tts": {
                    "engine": self.config.tts.engine,
                    "language": self.config.tts.language,
                    "available": self._tts_engine is not None,
                    "error": self._tts_error or None,
                },
                "audio_devices": {
                    "input": self.config.audio.input_device or "(default)",
                    "output": self.config.audio.output_device or "(default)",
                },
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
            },
        }

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
        """Handle a speech (TTS) request.

        Accepts override fields from the request body: engine, language,
        voice, speed. Falls back to the engine's TTSConfig for any field
        not provided.

        Args:
            body: Request body with ``text`` (required) and optional
                ``engine``, ``language``, ``voice``, ``speed``.

        Returns:
            Response dict with status and duration.
        """
        text = body.get("text", "")
        if not text:
            return {"status": "error", "error": "No text provided"}

        from dictare.config import TTSConfig
        from dictare.tts import get_cached_tts_engine

        # Build TTSConfig with overrides from request body
        has_override = any(k in body for k in ("engine", "language", "voice", "speed"))

        if has_override:
            base = self.config.tts
            tts_config = TTSConfig(
                engine=body.get("engine") or base.engine,
                language=body.get("language") or base.language,
                voice=body.get("voice") or base.voice,
                speed=body.get("speed") or base.speed,
            )
            try:
                tts = get_cached_tts_engine(tts_config)
            except ValueError as exc:
                return {"status": "error", "error": str(exc)}
        elif self._tts_engine is not None:
            tts = self._tts_engine
        else:
            error = self._tts_error or "TTS engine not loaded"
            return {"status": "error", "error": error}

        # Mic-pausing: blocking speak with PlayStart/PlayComplete events
        pause = not self.config.audio.headphones_mode

        start = time.time()

        if pause and self._controller is not None:
            from dictare.core.fsm import AppState, PlayCompleted, PlayStarted

            if self._controller.state != AppState.OFF:
                started = False
                try:
                    self._controller.send(PlayStarted(text="", source="tts"))
                    started = True
                except Exception:
                    pass

                try:
                    tts.speak(text)
                finally:
                    if started:
                        try:
                            self._controller.send(PlayCompleted(source="tts"))
                        except Exception:
                            pass
            else:
                tts.speak(text)
        else:
            tts.speak(text)

        duration_ms = int((time.time() - start) * 1000)

        return {"status": "ok", "duration_ms": duration_ms}

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
            "last_sse_agent=%r, agents=%s, hotkey=%r, start_listening=%r",
            self.agent_mode, self._current_agent_id,
            self._last_sse_agent_id,
            list(self._agents.keys()),
            self._hotkey is not None,
            start_listening,
        )

        self._running = True
        self._stats_start_time = time.time()

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
            )

        # Start audio streaming (always needed for VAD to work)
        _t0 = time.monotonic()
        if self._audio_manager:
            self._audio_manager.start_streaming(
                should_process=lambda: self._state_manager.should_process_audio,
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
                    if self._audio_manager.reconnect(self._audio_manager._on_audio_chunk):
                        logger.info("Audio reconnect succeeded")
                    else:
                        logger.error("Audio reconnect failed — waiting 30s before retry")
                        _deadline = time.monotonic() + 30.0
                        while self._running and time.monotonic() < _deadline:
                            time.sleep(0.5)
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
        if self._tts_worker_process is not None:
            logger.info("Stopping TTS worker (PID %d)", self._tts_worker_process.pid)
            self._tts_worker_process.terminate()
            try:
                self._tts_worker_process.wait(timeout=5)
            except Exception:
                self._tts_worker_process.kill()
            self._tts_worker_process = None


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
        engine.agent_mode, engine._current_agent_id,
    )
    return engine
