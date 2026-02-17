"""Core engine logic without UI dependencies."""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

from voxtype import __version__
from voxtype.agent.base import Agent
from voxtype.core.audio_manager import AudioManager
from voxtype.core.bus import bus
from voxtype.core.controller import StateController
from voxtype.core.events import EngineEvents
from voxtype.core.fsm import (
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
from voxtype.core.openvip_messages import create_message
from voxtype.hotkey.base import HotkeyListener
from voxtype.hotkey.tap_detector import TapDetector
from voxtype.pipeline import Pipeline, PipelineLoader
from voxtype.stt.base import STTEngine

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from voxtype.config import Config
    from voxtype.logging.jsonl import JSONLLogger


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


class VoxtypeEngine:
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

    def __init__(
        self,
        config: Config,
        events: EngineEvents | None = None,
        logger: JSONLLogger | None = None,
        agent_mode: bool = False,
        realtime: bool = False,
        hotkey_enabled: bool = True,
    ) -> None:
        """Initialize the engine.

        Args:
            config: Application configuration.
            events: Optional event handler for UI callbacks.
            logger: Optional JSONL logger for structured logging.
            agent_mode: Enable agent mode with auto-discovery.
            realtime: Enable realtime transcription feedback while speaking.
            hotkey_enabled: Enable hotkey listener. Set False for daemon mode
                           (macOS requires main thread for hotkey events).
        """
        self._hotkey_enabled = hotkey_enabled
        self.config = config
        self._events = events
        self._realtime = realtime
        self._partial_text = ""
        self._partial_text_lock = threading.Lock()  # Protects _partial_text access
        # Partial transcription: queue + single worker (avoids race conditions)
        self._partial_queue: Queue[Any] = Queue()
        self._partial_worker: threading.Thread | None = None
        self._partial_stop = threading.Event()

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

        # Agent mode: whether we're outputting to agents (vs keyboard/clipboard)
        self.agent_mode = agent_mode
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
        self._current_agent_id: str | None = None  # ID of currently selected agent
        self._agent_order: list[str] = []  # Ordered list of agent IDs for cycling

        # Pipelines for message processing
        self._pipeline = self._create_pipeline()
        self._executor_pipeline = self._create_executor_pipeline()
        self._input_manager: Any = None  # InputManager for keyboard/device inputs
        self._keyboard_agent: Any = None  # Special built-in agent for keyboard mode
        self._last_sse_agent_id: str | None = None  # Remember last SSE agent for mode switch

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
        self._realtime_stt: STTEngine | None = None  # Separate fast model for realtime
        self._hotkey: HotkeyListener | None = None
        # Status change callback — registered by AppController to push SSE updates.
        # Engine calls this on every status-relevant change (state, agents, mode).
        self._status_change_callback: Callable[[], None] | None = None

        # Loading progress tracking (for /status endpoint)
        self._loading_active = False
        self._loading_models: list[dict[str, Any]] = []
        # TTS engine (loaded at startup, None if unavailable)
        self._tts_engine: Any = None
        self._tts_error: str = ""

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
        if self._status_change_callback is not None:
            self._status_change_callback()

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
    RESERVED_AGENT_IDS = frozenset({"__keyboard__"})

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
        from voxtype.utils.hardware import is_mlx_available

        # Auto-detect MLX on Apple Silicon
        use_mlx = self.config.stt.hw_accel and is_mlx_available()

        engine: STTEngine
        if use_mlx:
            from voxtype.stt.mlx_whisper import MLXWhisperEngine
            engine = MLXWhisperEngine()
        else:
            from voxtype.stt.faster_whisper import FasterWhisperEngine
            engine = FasterWhisperEngine()

        engine.load_model(
            model_size or self.config.stt.model,
            device=self.config.stt.device,
            compute_type=self.config.stt.compute_type,
            console=None,  # No console in engine
            verbose=self.config.verbose,
            headless=headless,
        )

        return engine

    def _create_realtime_stt_engine(self) -> STTEngine:
        """Create fast STT engine for realtime partial transcriptions.

        Uses a smaller model (default: tiny) for low latency.
        """
        return self._create_stt_engine(model_size=self.config.stt.realtime_model)

    def _create_hotkey_listener(self) -> HotkeyListener:
        """Create hotkey listener with smart fallback."""
        errors: list[str] = []

        # Try evdev first on Linux
        if sys.platform == "linux":
            try:
                from voxtype.hotkey.evdev_listener import EvdevHotkeyListener

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
            from voxtype.hotkey.pynput_listener import PynputHotkeyListener

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
        if self.config.stt.hotwords:
            return self.config.stt.hotwords
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

    def init_components(self, *, headless: bool = False) -> None:
        """Initialize engine components (STT, VAD, audio, hotkey).

        Call this before start_runtime(). This loads models and creates
        the audio manager, but does not start listening.

        Args:
            headless: If True, skip all console output (for Engine/daemon mode).
        """
        from voxtype.utils.hardware import is_mlx_available
        from voxtype.utils.stats import get_model_load_time, save_model_load_time

        # Build model IDs for historical load time lookup
        model = self.config.stt.model
        if self.config.stt.hw_accel and is_mlx_available():
            stt_model_id = f"mlx-community/whisper-{model}"
        else:
            stt_model_id = f"faster-whisper-{model}"
        vad_model_id = "silero-vad"

        tts_engine_name = self.config.tts.engine

        self._loading_active = True
        self._loading_models = [
            {"name": "stt", "status": "pending", "start_time": 0, "elapsed": 0,
             "estimated": get_model_load_time(stt_model_id) or 25},
            {"name": "vad", "status": "pending", "start_time": 0, "elapsed": 0,
             "estimated": get_model_load_time(vad_model_id) or 25},
            {"name": "tts", "status": "pending", "start_time": 0, "elapsed": 0,
             "estimated": get_model_load_time(tts_engine_name) or 1},
        ]

        # Load STT model
        logger.debug("Loading STT model: %s (device=%s, compute=%s)",
                      stt_model_id, self.config.stt.device, self.config.stt.compute_type)
        self._loading_models[0]["start_time"] = time.time()
        self._loading_models[0]["status"] = "loading"
        self._stt = self._create_stt_engine(headless=headless)
        stt_elapsed = round(time.time() - self._loading_models[0]["start_time"], 1)
        self._loading_models[0]["elapsed"] = stt_elapsed
        self._loading_models[0]["status"] = "done"
        save_model_load_time(stt_model_id, stt_elapsed)
        logger.debug("STT model loaded in %.1fs", stt_elapsed)

        # Load separate fast model for realtime partial transcriptions
        if self._realtime:
            self._realtime_stt = self._create_realtime_stt_engine()

        # Note: Agent registration is handled externally by AgentRegistrar.
        # The registrar calls register_agent() to add agents before run().

        # Create audio manager with VAD
        logger.debug("Loading VAD model: %s", vad_model_id)
        self._loading_models[1]["start_time"] = time.time()
        self._loading_models[1]["status"] = "loading"
        self._audio_manager = AudioManager(
            config=self.config.audio,
            verbose=self.config.verbose,
        )
        self._audio_manager.initialize(
            on_speech_start=self._on_vad_speech_start,
            on_speech_end=self._on_vad_speech_end,
            on_max_speech=self._on_max_speech_duration,
            on_partial_audio=self._on_partial_audio if self._realtime else None,
            headless=headless,
        )
        vad_elapsed = round(time.time() - self._loading_models[1]["start_time"], 1)
        self._loading_models[1]["elapsed"] = vad_elapsed
        self._loading_models[1]["status"] = "done"
        save_model_load_time(vad_model_id, vad_elapsed)
        logger.debug("VAD model loaded in %.1fs", vad_elapsed)

        # Load TTS engine (optional — engine continues if unavailable)
        logger.debug("Loading TTS engine: %s", tts_engine_name)
        self._loading_models[2]["start_time"] = time.time()
        self._loading_models[2]["status"] = "loading"
        try:
            from voxtype.tts import get_cached_tts_engine

            self._tts_engine = get_cached_tts_engine(self.config.tts)
            # Ensure voice model is downloaded (piper downloads on first use)
            if hasattr(self._tts_engine, "_get_model_path"):
                self._tts_engine._get_model_path()
            tts_elapsed = round(time.time() - self._loading_models[2]["start_time"], 1)
            self._loading_models[2]["elapsed"] = tts_elapsed
            self._loading_models[2]["status"] = "done"
            save_model_load_time(tts_engine_name, tts_elapsed)
            logger.debug("TTS engine loaded in %.1fs", tts_elapsed)
        except ValueError as exc:
            tts_elapsed = round(time.time() - self._loading_models[2]["start_time"], 1)
            self._loading_models[2]["elapsed"] = tts_elapsed
            self._loading_models[2]["status"] = "error"
            self._tts_error = str(exc)
            logger.warning(
                "TTS engine '%s' not available — fix: voxtype dependencies resolve",
                tts_engine_name,
            )

        # Start partial transcription worker if realtime mode
        if self._realtime:
            self._partial_stop.clear()
            self._partial_worker = threading.Thread(
                target=self._partial_worker_loop,
                daemon=True,
                name="partial-transcription-worker",
            )
            self._partial_worker.start()

        # Create hotkey listener for toggle (if available and enabled)
        # Note: hotkey disabled in daemon mode - macOS requires main thread
        if self._hotkey_enabled:
            try:
                self._hotkey = self._create_hotkey_listener()
            except RuntimeError:
                self._hotkey = None
        else:
            self._hotkey = None

        # Loading complete — notify SSE subscribers to clear loading state
        self._loading_active = False
        self._notify_status()

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

    def _on_partial_audio(self, audio_data: Any) -> None:
        """Handle partial audio during speech for realtime feedback."""
        if not self._realtime or self._stt is None:
            return

        # Put chunk in queue - single worker will process it
        self._partial_queue.put(audio_data.copy())

    def _partial_worker_loop(self) -> None:
        """Single worker thread for partial transcriptions.

        Uses the fast realtime STT engine (tiny model) for low latency.
        No lock needed since _realtime_stt is only used by this thread.
        """
        while not self._partial_stop.is_set():
            try:
                audio_data = self._partial_queue.get(timeout=0.1)
            except Empty:
                continue

            # Drain queue: keep only the latest chunk to avoid lag
            while True:
                try:
                    audio_data = self._partial_queue.get_nowait()
                except Empty:
                    break

            # Transcribe the latest chunk with fast realtime model
            try:
                if self._realtime_stt is None:
                    continue
                result = self._realtime_stt.transcribe(
                    audio_data,
                    language=self.config.stt.language,
                    task="translate" if self.config.stt.translate else "transcribe",
                )
                text = result.text
                if text:
                    with self._partial_text_lock:
                        self._partial_text = text
            except Exception:
                logger.debug("partial transcription error", exc_info=True)

    def _on_vad_speech_end(self, audio_data: Any) -> None:
        """Handle VAD speech end detection."""
        # Capture agent NOW, before sending event
        # This ensures audio goes to the agent that was active when speech ended
        captured_agent = self._get_current_agent()

        if self._logger:
            sample_rate = self._audio_manager.sample_rate if self._audio_manager else self.config.audio.sample_rate
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
        if self._realtime:
            with self._partial_text_lock:
                self._partial_text = ""

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
                        beam_size=self.config.stt.beam_size,
                        max_repetitions=self.config.stt.max_repetitions,
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
                    audio_duration = len(audio_data) / self.config.audio.sample_rate
                    self._stats_count += 1
                    self._stats_chars += len(text)
                    self._stats_words += len(text.split())
                    self._stats_audio_seconds += audio_duration
                    self._stats_transcription_seconds += transcribe_time

                    # Log transcription
                    if self._logger:
                        duration_ms = audio_duration * 1000
                        self._logger.log_transcription(
                            text=text,
                            duration_ms=duration_ms,
                            language=self.config.stt.language,
                        )

                    # Check if user has turned off listening
                    if self.is_off:
                        return

            except Exception as e:
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

            self._stats_injection_seconds += time.time() - inject_start

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
            return  # Already in this mode

        if want_agent_mode:
            # Switch to agents: restore last SSE agent as current
            self.agent_mode = True
            restore_id = self._last_sse_agent_id
            real_agents = self.visible_agents
            if restore_id and restore_id in self._agents:
                self._current_agent_id = restore_id
            elif real_agents:
                self._current_agent_id = real_agents[0]
            self.speak_text("agent mode")
        else:
            # Switch to keyboard: save current agent, make __keyboard__ current
            if self._current_agent_id and self._current_agent_id != "__keyboard__":
                self._last_sse_agent_id = self._current_agent_id
            self._current_agent_id = "__keyboard__"
            self.agent_mode = False
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

        # If this is the first non-reserved agent, make it current
        if self._current_agent_id is None and agent.id not in self.RESERVED_AGENT_IDS:
            self._current_agent_id = agent.id


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
            "transcription_mode": "transcription mode",
            "command_mode": "command mode",
            "agent": "agent",
            "voice": "Samantha",
        }

        phrases_path = Path.home() / ".config" / "voxtype" / "tts_phrases.json"
        if phrases_path.exists():
            try:
                with open(phrases_path) as f:
                    custom = json.load(f)
                return {**default_phrases, **custom}
            except Exception:
                pass

        return default_phrases

    def speak_text(self, text: str) -> None:
        """Speak text using the pre-loaded TTS engine, optionally pausing the mic.

        Args:
            text: Text to speak.
        """
        if self._tts_engine is None:
            logger.warning("speak_text(%r): TTS engine not loaded", text)
            return

        from voxtype.audio.beep import get_sound_for_event

        enabled, _ = get_sound_for_event(self.config.audio, "agent_announce")
        if not enabled:
            return

        from voxtype.audio.beep import play_audio

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
        The prefix is configurable via ~/.config/voxtype/tts_phrases.json.

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
        from voxtype.core.fsm import AppState

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
                "name": "Voxtype",
                "version": __version__,
                "mode": "agents" if self.agent_mode else "keyboard",
                "state": stt_state,
                "uptime_seconds": uptime,
                "stt": {
                    "model_name": self.config.stt.model,
                    "device": getattr(self._stt, "_device", self.config.stt.device),
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
                "permissions": self._get_permissions(),
                "loading": {
                    "active": self._loading_active,
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

        from voxtype.platform.permissions import (
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

        from voxtype.config import TTSConfig
        from voxtype.tts import get_cached_tts_engine

        # Build TTSConfig with overrides from request body
        has_override = any(k in body for k in ("engine", "language", "voice", "speed"))

        if has_override:
            base = self.config.tts
            tts_config = TTSConfig(
                engine=body.get("engine", base.engine),
                language=body.get("language", base.language),
                voice=body.get("voice", base.voice),
                speed=body.get("speed", base.speed),
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
            from voxtype.core.fsm import AppState, PlayCompleted, PlayStarted

            if self._controller.state != AppState.OFF:
                try:
                    play_id = self._controller.get_next_play_id()
                    self._controller.send(PlayStarted(text="", source="tts"))
                except Exception:
                    play_id = None

                try:
                    tts.speak(text)
                finally:
                    if play_id is not None:
                        try:
                            self._controller.send(
                                PlayCompleted(play_id=play_id, source="tts")
                            )
                        except Exception:
                            pass
            else:
                tts.speak(text)
        else:
            tts.speak(text)

        duration_ms = int((time.time() - start) * 1000)

        return {"status": "ok", "duration_ms": duration_ms}

    def handle_protocol_command(self, body: dict) -> dict:
        """Handle an OpenVIP protocol command.

        Protocol commands: stt.start, stt.stop, stt.toggle, engine.shutdown, ping.

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
            self._running = False
            return {"status": "ok"}
        elif command == "ping":
            return {"status": "ok", "pong": True}

        return {"status": "error", "error": f"Unknown protocol command: {command}"}

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
        if self._audio_manager:
            self._audio_manager.start_streaming(
                should_process=lambda: self._state_manager.should_process_audio,
                is_running=lambda: self._running,
            )

        # Transition to initial state
        if start_listening:
            old_state = self.state
            self._state_manager.transition(AppState.LISTENING)
            self._emit("on_state_change", old_state, AppState.LISTENING, "start")

    def run(self) -> None:
        """Run the engine main loop (blocking).

        Call start_runtime() first. This keeps the main thread alive and
        handles audio device reconnection.
        """
        try:
            while self._running:
                time.sleep(0.1)
                if self._audio_manager and self._audio_manager.needs_reconnect():
                    if not self._audio_manager.reconnect(self._audio_manager._on_audio_chunk):
                        break
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

        # Stop partial transcription worker (daemon thread, don't block long)
        if self._partial_worker:
            self._partial_stop.set()
            self._partial_worker.join(timeout=0.3)
            self._partial_worker = None

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


def create_engine(
    config: Config,
    events: EngineEvents,
    *,
    logger: JSONLLogger | None = None,
    agent_mode: bool | None = None,
    realtime: bool | None = None,
    hotkey_enabled: bool = True,
) -> VoxtypeEngine:
    """Create a VoxtypeEngine.

    This is the shared initialization logic used by both CLI (voxtype listen)
    and daemon. Ensures consistent behavior.

    In agent mode, agents self-register via SSE connection to the HTTP server.
    In keyboard mode, a KeyboardAgent is created and managed internally.

    Args:
        config: Application configuration.
        events: Event handler callbacks.
        logger: Optional JSONL logger.
        agent_mode: Override config.output.mode. If None, uses config.
        realtime: Enable realtime transcription. Defaults to False.
        hotkey_enabled: Enable hotkey listener. Set False for daemon mode
                       (macOS requires main thread for hotkey events).

    Returns:
        Configured VoxtypeEngine instance.
    """
    # Use overrides or fall back to config/defaults
    effective_agent_mode = agent_mode if agent_mode is not None else (config.output.mode == "agents")
    effective_realtime = realtime if realtime is not None else False  # realtime is CLI-only, default off

    engine = VoxtypeEngine(
        config=config,
        events=events,
        logger=logger,
        agent_mode=effective_agent_mode,
        realtime=effective_realtime,
        hotkey_enabled=hotkey_enabled,
    )

    # Always create KeyboardAgent — mode switch just changes current_agent_id
    from voxtype.agent.keyboard import KeyboardAgent

    keyboard_agent = KeyboardAgent(config)
    engine._keyboard_agent = keyboard_agent
    engine.register_agent(keyboard_agent)

    if not effective_agent_mode:
        # Keyboard mode: make __keyboard__ the current agent
        engine._current_agent_id = "__keyboard__"

    return engine
