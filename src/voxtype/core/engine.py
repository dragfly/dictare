"""Core engine logic without UI dependencies."""

from __future__ import annotations

import sys
import threading
import time
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

from voxtype.core.audio_manager import AudioManager
from voxtype.core.events import EngineEvents, InjectionResult, TranscriptionResult
from voxtype.core.state import AppState, ProcessingMode, StateManager
from voxtype.hotkey.base import HotkeyListener
from voxtype.injection.base import TextInjector
from voxtype.stt.base import STTEngine

if TYPE_CHECKING:
    from voxtype.config import Config
    from voxtype.llm import LLMProcessor, LLMResponse
    from voxtype.logging.jsonl import JSONLLogger


class VoxtypeEngine:
    """Core engine for voice-to-text processing.

    Coordinates audio capture, STT, hotkey detection, and text injection.
    Uses LLM-first architecture: ALL transcribed text goes through the LLM
    which decides what action to take.

    This class contains NO UI code - use VoxtypeApp for the full application
    with console output, status panels, and audio feedback.
    """

    # Minimum recording duration in seconds
    MIN_RECORDING_DURATION = 0.3

    # Double-tap detection threshold in seconds
    DOUBLE_TAP_THRESHOLD = 0.4

    # Default VAD silence duration in milliseconds
    DEFAULT_VAD_SILENCE_MS = 1200

    def __init__(
        self,
        config: Config,
        events: EngineEvents | None = None,
        logger: JSONLLogger | None = None,
        agents: list[str] | None = None,
        realtime: bool = False,
    ) -> None:
        """Initialize the engine.

        Args:
            config: Application configuration.
            events: Optional event handler for UI callbacks.
            logger: Optional JSONL logger for structured logging.
            agents: List of agent IDs for multi-output mode (socket-based).
            realtime: Enable realtime transcription feedback while speaking.
        """
        self.config = config
        self._events = events
        self._realtime = realtime
        self._partial_text = ""
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
        self.trigger_phrase = config.command.wake_word or None
        self.agents = agents or []
        # State machine handles all state (OFF/LISTENING/RECORDING/etc)
        self._state_manager = StateManager(initial_state=AppState.OFF)
        self._running = False
        self._injection_lock = threading.Lock()  # Lock for text injection
        self._logger = logger

        # Agent state
        self._current_agent_index = 0
        self._input_manager: Any = None  # InputManager for keyboard/device inputs

        # Processing mode: TRANSCRIPTION (fast, no LLM) or COMMAND (LLM)
        self._processing_mode = ProcessingMode(config.command.mode)

        # Double-tap detection
        self._last_tap_time: float = 0.0
        self._pending_single_tap: threading.Timer | None = None

        # Initialize components
        self._audio_manager: AudioManager | None = None
        self._stt: STTEngine | None = None
        self._hotkey: HotkeyListener | None = None
        self._injector: TextInjector | None = None

        # LLM processor for command mode
        self._llm_processor: LLMProcessor | None = None

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
                    pass  # Don't let UI errors crash the engine

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

    @property
    def mode(self) -> ProcessingMode:
        """Get current processing mode."""
        return self._processing_mode

    @property
    def current_agent(self) -> str | None:
        """Get the name of the current agent, or None if no agents."""
        if self.agents:
            return self.agents[self._current_agent_index]
        return None

    @property
    def current_agent_index(self) -> int:
        """Get the index of the current agent (0-based)."""
        return self._current_agent_index

    # -------------------------------------------------------------------------
    # Session Stats (read-only access for UI)
    # -------------------------------------------------------------------------

    @property
    def stats_chars(self) -> int:
        """Total characters transcribed this session."""
        return self._stats_chars

    @property
    def stats_words(self) -> int:
        """Total words transcribed this session."""
        return self._stats_words

    @property
    def stats_audio_seconds(self) -> float:
        """Total audio duration processed this session."""
        return self._stats_audio_seconds

    @property
    def stats_transcription_seconds(self) -> float:
        """Total transcription time this session."""
        return self._stats_transcription_seconds

    @property
    def stats_injection_seconds(self) -> float:
        """Total injection time this session."""
        return self._stats_injection_seconds

    @property
    def stats_count(self) -> int:
        """Total number of transcriptions this session."""
        return self._stats_count

    @property
    def stats_start_time(self) -> float | None:
        """Session start time (Unix timestamp)."""
        return self._stats_start_time

    # -------------------------------------------------------------------------
    # Factory Methods
    # -------------------------------------------------------------------------

    def _create_stt_engine(self) -> STTEngine:
        """Create and load STT engine."""
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
            self.config.stt.model_size,
            device=self.config.stt.device,
            compute_type=self.config.stt.compute_type,
            console=None,  # No console in engine
            verbose=self.config.verbose,
        )

        return engine

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

    def _get_current_agent_id(self) -> str | None:
        """Get the current agent ID for socket-based injection."""
        if self.agents:
            return self.agents[self._current_agent_index]
        return None

    def _get_hotwords(self) -> str | None:
        """Build hotwords string from config + wake_word."""
        parts = []

        # Add config hotwords
        if self.config.stt.hotwords:
            parts.append(self.config.stt.hotwords)

        # Add wake word (lowercased, normalized)
        if self.trigger_phrase:
            normalized = self.trigger_phrase.lower().replace(",", " ").strip()
            if normalized and normalized not in parts:
                parts.append(normalized)

        return ",".join(parts) if parts else None

    def _create_injector(self) -> TextInjector:
        """Create text injector based on config.output.method."""
        # Agent output mode - send OpenVIP messages via Unix socket
        agent_id = self._get_current_agent_id()
        if agent_id or self.config.output.method == "agent":
            from voxtype.injection.socket import SocketInjector
            return SocketInjector(agent_id or "default")

        # Keyboard mode - platform-specific injector
        if sys.platform == "darwin":
            from voxtype.injection.quartz import QuartzInjector

            injector = QuartzInjector()
            if not injector.is_available():
                raise RuntimeError(
                    "Quartz text injection not available. "
                    "Grant Accessibility permission in System Preferences > "
                    "Security & Privacy > Privacy > Accessibility"
                )
            return injector
        else:
            from voxtype.injection.ydotool import YdotoolInjector

            injector = YdotoolInjector()
            if not injector.is_available():
                raise RuntimeError(
                    "ydotool not available. Ensure ydotoold is running:\n"
                    "  sudo ydotoold &\n"
                    "Or install ydotool: apt install ydotool / pacman -S ydotool"
                )
            return injector

    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------

    def _init_vad_components(self) -> None:
        """Initialize components for VAD mode."""
        self._stt = self._create_stt_engine()
        self._injector = self._create_injector()

        # Create audio manager with VAD
        self._audio_manager = AudioManager(
            config=self.config.audio,
            verbose=self.config.verbose,
        )
        self._audio_manager.initialize(
            on_speech_start=self._on_vad_speech_start,
            on_speech_end=self._on_vad_speech_end,
            on_max_speech=self._on_max_speech_duration,
            on_partial_audio=self._on_partial_audio if self._realtime else None,
            on_vad_loading=lambda: self._emit("on_vad_loading"),
        )
        # Set reconnect callbacks
        self._audio_manager.set_reconnect_callbacks(
            on_attempt=lambda n: self._emit("on_device_reconnect_attempt", n),
            on_success=lambda name: self._emit("on_device_reconnect_success", name),
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

        # Create LLM processor for command mode
        self._init_llm_processor()

        # Create hotkey listener for toggle (if available)
        try:
            self._hotkey = self._create_hotkey_listener()
        except RuntimeError:
            self._hotkey = None

    def _init_llm_processor(self) -> None:
        """Initialize the LLM-first processor."""
        from voxtype.llm import LLMProcessor

        self._llm_processor = LLMProcessor(
            trigger_phrase=self.trigger_phrase,
            ollama_model=self.config.command.ollama_model,
            ollama_timeout=self.config.command.ollama_timeout,
            console=None,  # No console in engine
        )

    # -------------------------------------------------------------------------
    # VAD Callbacks
    # -------------------------------------------------------------------------

    def _on_max_speech_duration(self) -> None:
        """Handle max speech duration reached in VAD mode."""
        self._emit("on_max_duration_reached")

    def _on_vad_speech_start(self) -> None:
        """Handle VAD speech start detection."""
        # Try to transition IDLE → RECORDING
        if not self._state_manager.try_transition(AppState.RECORDING):
            return

        self._emit("on_recording_start")

        if self._logger:
            self._logger.log_vad_event("speech_start")

    def _on_partial_audio(self, audio_data: Any) -> None:
        """Handle partial audio during speech for realtime feedback."""
        if not self._realtime or self._stt is None:
            return

        # Put chunk in queue - single worker will process it
        self._partial_queue.put(audio_data.copy())

    def _partial_worker_loop(self) -> None:
        """Single worker thread for partial transcriptions."""
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

            # Transcribe the latest chunk
            try:
                with self._stt_lock:
                    assert self._stt is not None
                    text = self._stt.transcribe(
                        audio_data,
                        language=self.config.stt.language,
                    )
                if text and text != self._partial_text:
                    self._partial_text = text
                    self._emit("on_partial_transcription", text)
            except Exception:
                pass  # Ignore partial transcription errors

    def _on_vad_speech_end(self, audio_data: Any) -> None:
        """Handle VAD speech end detection."""
        # Try to transition to TRANSCRIBING (valid from IDLE or RECORDING)
        if not self._state_manager.try_transition(AppState.TRANSCRIBING):
            # Can't transition - queue audio if busy transcribing
            if self.state == AppState.TRANSCRIBING and self._audio_manager:
                self._audio_manager.queue_audio(audio_data)
            return

        # Calculate duration
        sample_rate = self._audio_manager.sample_rate if self._audio_manager else self.config.audio.sample_rate
        duration_ms = len(audio_data) / sample_rate * 1000

        self._emit("on_recording_end", duration_ms)

        if self._logger:
            self._logger.log_vad_event("speech_end", duration_ms=duration_ms)

        # Check minimum duration
        min_samples = int(sample_rate * self.MIN_RECORDING_DURATION)
        if len(audio_data) < min_samples:
            old_state = self.state
            self._state_manager.reset_to_listening()
            self._emit("on_state_change", old_state, AppState.LISTENING, "audio_too_short")
            return

        # Transcribe and process with LLM
        self._transcribe_and_process(audio_data)

    # -------------------------------------------------------------------------
    # Transcription
    # -------------------------------------------------------------------------

    def _transcribe_and_process(self, audio_data: Any) -> None:
        """Transcribe audio and process with LLM-first architecture."""
        # For realtime mode: clear partial text
        if self._realtime:
            self._partial_text = ""

        def do_transcribe() -> None:
            try:
                if not self._stt:
                    return

                # Track transcription time
                transcribe_start = time.time()
                with self._stt_lock:
                    text = self._stt.transcribe(
                        audio_data,
                        language=self.config.stt.language,
                        hotwords=self._get_hotwords(),
                        beam_size=self.config.stt.beam_size,
                        max_repetitions=self.config.stt.max_repetitions,
                    )
                transcribe_time = time.time() - transcribe_start

                if text:
                    # Update session stats
                    audio_duration = len(audio_data) / self.config.audio.sample_rate
                    self._stats_count += 1
                    self._stats_chars += len(text)
                    self._stats_words += len(text.split())
                    self._stats_audio_seconds += audio_duration
                    self._stats_transcription_seconds += transcribe_time

                    # Emit transcription event
                    self._emit(
                        "on_transcription",
                        TranscriptionResult(
                            text=text,
                            audio_duration_seconds=audio_duration,
                            transcription_seconds=transcribe_time,
                        ),
                    )

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

                    # Process based on mode
                    if self._processing_mode == ProcessingMode.TRANSCRIPTION:
                        # Transcription mode: fast inject, no LLM
                        self._inject_text(text)
                    elif self._processing_mode == ProcessingMode.COMMAND and self._llm_processor:
                        # Command mode: process through LLM
                        response = self._llm_processor.process(text)
                        self._execute_llm_response(response, text)
                    else:
                        # Fallback: just inject
                        self._inject_text(text)
            except Exception as e:
                if self._logger:
                    self._logger.log_error(str(e), context="transcribe_and_process")
                self._emit("on_error", str(e), "transcribe_and_process")
            finally:
                old_state = self.state
                self._state_manager.reset_to_listening()
                self._emit("on_state_change", old_state, AppState.LISTENING, "transcription_complete")
                # Process queued audio if any
                self._process_queued_audio()

        thread = threading.Thread(target=do_transcribe, daemon=True)
        thread.start()

    def _process_queued_audio(self) -> None:
        """Process any queued audio from speech that occurred during transcription."""
        if not self._audio_manager:
            return

        sample_rate = self._audio_manager.sample_rate
        min_samples = int(sample_rate * self.MIN_RECORDING_DURATION)

        while self._audio_manager.has_queued_audio:
            audio_data = self._audio_manager.pop_queued_audio()
            if not audio_data:
                continue

            # Check minimum duration
            if len(audio_data) < min_samples:
                continue

            # Found valid audio - process it and return
            self._state_manager.transition(AppState.TRANSCRIBING)
            self._transcribe_and_process(audio_data)
            return

    # -------------------------------------------------------------------------
    # LLM Response Execution
    # -------------------------------------------------------------------------

    def _execute_llm_response(self, response: LLMResponse, original_text: str) -> None:
        """Execute the action decided by the LLM."""
        from voxtype.llm.models import Action

        # Log the LLM decision
        if self._logger:
            current_llm_state = self._llm_processor.state.value if self._llm_processor else "unknown"
            self._logger.log(
                "llm_decision",
                current_state=current_llm_state,
                text=original_text,
                action=response.action.value,
                new_state=response.new_state.value if response.new_state else None,
                command=response.command.value if response.command else None,
                confidence=response.confidence,
                backend=response.backend,
                override_reason=response.override_reason,
                raw_llm_response=response.raw_llm_response,
                text_to_inject=response.text_to_inject,
            )

        if response.action == Action.IGNORE:
            return

        if response.action == Action.CHANGE_STATE:
            if response.new_state == AppState.LISTENING:
                self._enter_listening_mode()
            elif response.new_state == AppState.OFF:
                self._exit_listening_mode()
            return

        if response.action == Action.EXECUTE:
            self._execute_command(response.command, response.command_args)
            return

        if response.action == Action.INJECT:
            if response.text_to_inject:
                self._state_manager.transition(AppState.INJECTING)
                self._inject_text(response.text_to_inject)

    def _execute_command(self, command: Any, args: dict[str, Any] | None) -> None:
        """Execute a voice command."""
        from voxtype.llm.models import Command

        if command == Command.REPEAT:
            if self._llm_processor and self._llm_processor.last_injection:
                self._inject_text(self._llm_processor.last_injection)

    # -------------------------------------------------------------------------
    # Text Injection
    # -------------------------------------------------------------------------

    def _inject_text(self, text: str) -> None:
        """Inject text into the target.

        Each injector handles message termination based on auto_enter:
        - auto_enter=true: text + submit (Enter for keyboard, x_submit for socket)
        - auto_enter=false: text + visual newline (Shift+Enter for keyboard, etc.)
        """
        if self._injector:
            method = self._injector.get_name()

            # Lock to prevent concurrent injections
            with self._injection_lock:
                inject_start = time.time()
                success = self._injector.type_text(
                    text,
                    delay_ms=self.config.output.typing_delay_ms,
                    auto_enter=self.config.output.auto_enter,
                )
                self._stats_injection_seconds += time.time() - inject_start

            # Emit injection event
            self._emit(
                "on_injection",
                InjectionResult(text=text, success=success, method=method),
            )

            # Log injection
            if self._logger:
                enter_sent = getattr(self._injector, '_enter_sent', None)
                self._logger.log_injection(
                    text=text,
                    method=method,
                    success=success,
                    auto_enter=self.config.output.auto_enter,
                    enter_sent=enter_sent,
                )

    # -------------------------------------------------------------------------
    # State Control
    # -------------------------------------------------------------------------

    def _enter_listening_mode(self, trigger: str = "voice_command") -> None:
        """Enter LISTENING mode."""
        old_state = self.state
        if self._state_manager.try_transition(AppState.LISTENING):
            self._emit("on_state_change", old_state, AppState.LISTENING, trigger)

            if self._logger:
                self._logger.log_state_change(
                    old_state="IDLE",
                    new_state="LISTENING",
                    trigger=trigger,
                )

    def _exit_listening_mode(self, trigger: str = "voice_command") -> None:
        """Exit LISTENING mode."""
        old_state = self.state
        if self._state_manager.try_transition(AppState.OFF):
            self._emit("on_state_change", old_state, AppState.OFF, trigger)

            if self._logger:
                self._logger.log_state_change(
                    old_state="LISTENING",
                    new_state="IDLE",
                    trigger=trigger,
                )

    def _on_hotkey_toggle(self) -> None:
        """Handle hotkey press in VAD mode."""
        current_time = time.time()
        time_since_last = current_time - self._last_tap_time
        self._last_tap_time = current_time

        # Double tap detection
        if time_since_last < self.DOUBLE_TAP_THRESHOLD:
            if self._pending_single_tap:
                self._pending_single_tap.cancel()
                self._pending_single_tap = None
            self._switch_processing_mode()
            return

        # Schedule single tap
        if self._pending_single_tap:
            self._pending_single_tap.cancel()
        self._pending_single_tap = threading.Timer(
            self.DOUBLE_TAP_THRESHOLD,
            self._toggle_listening
        )
        self._pending_single_tap.start()

    def _toggle_listening(self) -> None:
        """Toggle listening on/off using state machine."""
        current = self.state
        old_state = current

        if current == AppState.OFF:
            # OFF → LISTENING
            if self._state_manager.try_transition(AppState.LISTENING):
                self._emit("on_state_change", old_state, AppState.LISTENING, "hotkey_toggle")
        else:
            # Any active state → OFF (hotkey must always work to turn off)
            if self._state_manager.try_transition(AppState.OFF):
                self._emit("on_state_change", old_state, AppState.OFF, "hotkey_toggle")

        # Sync LLM processor state
        if self._llm_processor:
            self._llm_processor.set_listening(self.is_listening)

    def _switch_processing_mode(self) -> None:
        """Switch between transcription and command mode."""
        if self._processing_mode == ProcessingMode.TRANSCRIPTION:
            self._processing_mode = ProcessingMode.COMMAND
        else:
            self._processing_mode = ProcessingMode.TRANSCRIPTION

        # Sync LLM processor state
        if self._llm_processor:
            self._llm_processor.set_listening(self.is_listening)

        self._emit("on_mode_change", self._processing_mode)

    def _set_listening(self, on: bool) -> None:
        """Set listening state on/off using state machine."""
        old_state = self.state

        if on and self.is_off:
            if self._state_manager.try_transition(AppState.LISTENING):
                self._emit("on_state_change", old_state, AppState.LISTENING, "set_listening")
        elif not on and self.is_listening:
            if self._state_manager.try_transition(AppState.OFF):
                self._emit("on_state_change", old_state, AppState.OFF, "set_listening")

        # Sync LLM processor state
        if self._llm_processor:
            self._llm_processor.set_listening(self.is_listening)

    # -------------------------------------------------------------------------
    # Agent Control
    # -------------------------------------------------------------------------

    def _switch_agent(self, direction: int) -> None:
        """Switch to next/previous agent."""
        if not self.agents:
            return

        # Circular navigation
        self._current_agent_index = (self._current_agent_index + direction) % len(self.agents)
        new_agent = self.agents[self._current_agent_index]

        # Update the injector to write to the new agent file
        self._injector = self._create_injector()

        self._emit("on_agent_change", new_agent, self._current_agent_index)

    def _switch_to_agent_by_name(self, name: str) -> bool:
        """Switch to a specific agent by name."""
        if not self.agents:
            return False

        name_lower = name.lower()

        # Try exact match first
        for i, agent in enumerate(self.agents):
            if agent.lower() == name_lower:
                self._current_agent_index = i
                self._injector = self._create_injector()
                self._emit("on_agent_change", agent, i)
                return True

        # Try partial match
        for i, agent in enumerate(self.agents):
            if name_lower in agent.lower():
                self._current_agent_index = i
                self._injector = self._create_injector()
                self._emit("on_agent_change", agent, i)
                return True

        return False

    def _switch_to_agent_by_index(self, index: int) -> bool:
        """Switch to a specific agent by index (1-based)."""
        if not self.agents:
            return False

        idx = index - 1
        if idx < 0 or idx >= len(self.agents):
            return False

        self._current_agent_index = idx
        agent = self.agents[idx]
        self._injector = self._create_injector()
        self._emit("on_agent_change", agent, idx)
        return True

    def _repeat_last_injection(self) -> None:
        """Repeat the last injected text."""
        if self._llm_processor and self._llm_processor.last_injection:
            self._inject_text(self._llm_processor.last_injection)

    def _send_submit(self) -> None:
        """Send submit (Enter key) to the target."""
        if self._injector:
            self._injector.send_submit()

    def _discard_current(self) -> None:
        """Discard current recording/transcription."""
        if self._audio_manager:
            self._audio_manager.clear_queue()
            self._audio_manager.flush_vad()

        if self.state == AppState.RECORDING:
            self._state_manager.transition(AppState.LISTENING)


    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Start the engine main loop."""
        self._init_vad_components()

        self._running = True
        self._stats_start_time = time.time()

        try:
            # Start hotkey listener
            if self._hotkey:
                self._hotkey.start(
                    on_press=self._on_hotkey_toggle,
                    on_release=lambda: None,
                )

            # Transition OFF → LISTENING
            old_state = self.state
            self._state_manager.transition(AppState.LISTENING)
            self._emit("on_state_change", old_state, AppState.LISTENING, "start")

            # Sync LLM processor state
            if self._llm_processor:
                self._llm_processor.set_listening(True)

            if self._audio_manager:
                self._audio_manager.start_streaming(
                    is_listening=lambda: self._state_manager.should_process_audio,
                    is_running=lambda: self._running,
                )

            # Keep main thread alive
            while self._running:
                time.sleep(0.1)
                if self._audio_manager and self._audio_manager.needs_reconnect():
                    if not self._audio_manager.reconnect(self._audio_manager._on_audio_chunk):
                        break
        except KeyboardInterrupt:
            pass

    def stop(self) -> None:
        """Stop the engine."""
        import gc

        self._running = False

        # Force transition to OFF
        self._state_manager.transition(AppState.OFF, force=True)

        # Stop partial transcription worker
        if self._partial_worker:
            self._partial_stop.set()
            self._partial_worker.join(timeout=1.0)
            self._partial_worker = None

        # Close audio/VAD
        if self._audio_manager:
            self._audio_manager.flush_vad()
            self._audio_manager.close()

        gc.collect()

        # Cancel pending single tap timer
        if self._pending_single_tap:
            self._pending_single_tap.cancel()
            self._pending_single_tap = None

        if self._input_manager:
            self._input_manager.stop()

        if self._hotkey:
            self._hotkey.stop()
