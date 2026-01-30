"""Core engine logic without UI dependencies."""

from __future__ import annotations

import sys
import threading
import time
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

from voxtype.agent.base import Agent
from voxtype.core.audio_manager import AudioManager
from voxtype.core.controller import StateController
from voxtype.core.events import (
    AgentSwitchEvent,
    DiscardCurrentEvent,
    EngineEvents,
    HotkeyToggleEvent,
    InjectionResult,
    SetListeningEvent,
    SpeechEndEvent,
    SpeechStartEvent,
    TranscriptionCompleteEvent,
    TranscriptionResult,
)
from voxtype.core.openvip import create_message
from voxtype.core.state import AppState, StateManager
from voxtype.hotkey.base import HotkeyListener
from voxtype.hotkey.tap_detector import TapDetector
from voxtype.stt.base import STTEngine

if TYPE_CHECKING:
    from voxtype.config import Config
    from voxtype.logging.jsonl import JSONLLogger


class VoxtypeEngine:
    """Core engine for voice-to-text processing.

    Coordinates audio capture, STT, hotkey detection, and text injection.
    Implements OpenVIP v1.0 protocol for voice input.

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
        agent_mode: bool = False,
        realtime: bool = False,
    ) -> None:
        """Initialize the engine.

        Args:
            config: Application configuration.
            events: Optional event handler for UI callbacks.
            logger: Optional JSONL logger for structured logging.
            agent_mode: Enable agent mode with auto-discovery.
            realtime: Enable realtime transcription feedback while speaking.
        """
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
            on_recording_start=lambda: self._emit("on_recording_start"),
            on_recording_end=lambda ms: self._emit("on_recording_end", ms),
            on_state_change=lambda old, new, trigger: self._emit(
                "on_state_change", old, new, trigger
            ),
            on_agent_change=lambda name, idx: self._emit("on_agent_change", name, idx),
        )
        self._controller.set_engine(self)

        self._running = False
        self._injection_lock = threading.Lock()  # Lock for text injection
        self._logger = logger

        # Agent state
        self._current_agent_id: str | None = None  # ID of currently selected agent
        self._agent_order: list[str] = []  # Ordered list of agent IDs for cycling
        self._input_manager: Any = None  # InputManager for keyboard/device inputs

        # Tap detection (isolated state machine)
        # Single tap: toggle listening on/off
        # Double tap: switch to next agent
        self._tap_detector = TapDetector(
            threshold=self.DOUBLE_TAP_THRESHOLD,
            on_single_tap=lambda: self._controller.send(HotkeyToggleEvent(source="hotkey")),
            on_double_tap=lambda: self._controller.send(AgentSwitchEvent(direction=1, source="hotkey")),
        )

        # Initialize components
        self._audio_manager: AudioManager | None = None
        self._stt: STTEngine | None = None
        self._realtime_stt: STTEngine | None = None  # Separate fast model for realtime
        self._hotkey: HotkeyListener | None = None
        # Note: No more _injector - each Agent handles its own transport

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
    def agents(self) -> list[str]:
        """Get list of registered agent IDs (for backward compatibility)."""
        return self._agent_order.copy()

    @property
    def current_agent(self) -> str | None:
        """Get the ID of the current agent, or None if no agents."""
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

    def _create_stt_engine(self, model_size: str | None = None) -> STTEngine:
        """Create and load STT engine.

        Args:
            model_size: Model size to load. If None, uses config.stt.model.
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

    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------

    def _init_vad_components(self) -> None:
        """Initialize components for VAD mode."""
        self._stt = self._create_stt_engine()

        # Load separate fast model for realtime partial transcriptions
        if self._realtime:
            self._realtime_stt = self._create_realtime_stt_engine()

        # Note: Agent registration is handled externally by AgentRegistrar.
        # The registrar calls register_agent() to add agents before run().

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

        # Create hotkey listener for toggle (if available)
        try:
            self._hotkey = self._create_hotkey_listener()
        except RuntimeError:
            self._hotkey = None

    # -------------------------------------------------------------------------
    # VAD Callbacks
    # -------------------------------------------------------------------------

    def _on_max_speech_duration(self) -> None:
        """Handle max speech duration reached in VAD mode."""
        self._emit("on_max_duration_reached")

    def _on_vad_speech_start(self) -> None:
        """Handle VAD speech start detection."""
        # Send event to controller - it handles the state transition
        self._controller.send(SpeechStartEvent(source="vad"))

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
                text = self._realtime_stt.transcribe(
                    audio_data,
                    language=self.config.stt.language,
                    task="translate" if self.config.stt.translate else "transcribe",
                )
                if text:
                    with self._partial_text_lock:
                        if text != self._partial_text:
                            self._partial_text = text
                            self._emit("on_partial_transcription", text)
            except Exception:
                pass  # Ignore partial transcription errors

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
            SpeechEndEvent(
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

        Called by StateController when SpeechEndEvent is processed.

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
            try:
                if not self._stt:
                    return

                # Track transcription time
                transcribe_start = time.time()
                task = "translate" if self.config.stt.translate else "transcribe"
                with self._stt_lock:
                    text = self._stt.transcribe(
                        audio_data,
                        language=self.config.stt.language,
                        hotwords=self._get_hotwords(),
                        beam_size=self.config.stt.beam_size,
                        max_repetitions=self.config.stt.max_repetitions,
                        task=task,
                    )
                transcribe_time = time.time() - transcribe_start

                if text:
                    transcribed_text = text

                    # Update session stats
                    audio_duration = len(audio_data) / self.config.audio.sample_rate
                    self._stats_count += 1
                    self._stats_chars += len(text)
                    self._stats_words += len(text.split())
                    self._stats_audio_seconds += audio_duration
                    self._stats_transcription_seconds += transcribe_time

                    # Emit transcription event (for UI)
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

            except Exception as e:
                if self._logger:
                    self._logger.log_error(str(e), context="transcribe_and_process")
                self._emit("on_error", str(e), "transcribe_and_process")
            finally:
                # Send completion event to controller (it handles state transition)
                self._controller.send(
                    TranscriptionCompleteEvent(
                        text=transcribed_text,
                        agent=captured_agent,
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
            if not audio_data:
                continue

            # Check minimum duration
            if len(audio_data) < min_samples:
                continue

            # Found valid audio - send as event (controller handles state)
            self._controller.send(
                SpeechEndEvent(
                    audio_data=audio_data,
                    agent=self._get_current_agent(),
                    source="queued",
                )
            )
            return

    # -------------------------------------------------------------------------
    # Text Injection
    # -------------------------------------------------------------------------

    def _inject_text(self, text: str, *, agent: Agent | None = None) -> None:
        """Inject text into the target agent.

        Uses OpenVIP message format - each agent handles its own transport:
        - KeyboardAgent: simulates keystrokes
        - SocketAgent: sends via Unix socket
        - SSEAgent: sends via Server-Sent Events
        - WebhookAgent: sends via HTTP POST

        Message termination based on auto_enter:
        - auto_enter=true: text + submit flag
        - auto_enter=false: text + visual newline flag

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

        # Build OpenVIP message with unique ID
        message = create_message(
            text,
            submit=auto_enter,
            visual_newline=not auto_enter,
        )

        # Lock to prevent concurrent injections
        error_msg: str | None = None
        with self._injection_lock:
            inject_start = time.time()

            if target_agent:
                # Send to agent - agent handles its own transport
                method = f"agent:{target_agent.id}"
                success = target_agent.send(message)

                # Set helpful error message for failures
                if not success:
                    error_msg = f"<agent '{target_agent.id}' not responding>"
            else:
                # No agent available
                method = "none"
                error_msg = "<no agents registered - use --agents or start an agent>"

            self._stats_injection_seconds += time.time() - inject_start

        # Emit injection event
        self._emit(
            "on_injection",
            InjectionResult(text=text, success=success, method=method, error=error_msg),
        )

        # Log injection
        if self._logger:
            self._logger.log_injection(
                text=text,
                method=method,
                success=success,
                auto_enter=auto_enter,
                enter_sent=None,  # Agents handle their own submission
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

    def _toggle_listening(self) -> None:
        """Toggle listening on/off - sends event to controller."""
        self._controller.send(HotkeyToggleEvent(source="api"))

    def _set_listening(self, on: bool) -> None:
        """Set listening state on/off - sends event to controller."""
        self._controller.send(SetListeningEvent(on=on, source="api"))

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

        # If this is the first agent, make it current
        if self._current_agent_id is None:
            self._current_agent_id = agent.id

        self._emit("on_agents_changed", self.agents)
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
        if self._agent_order:
            if was_current:
                # Switch to first agent
                self._current_agent_id = self._agent_order[0]
                self._emit("on_agent_change", self._current_agent_id, 0)
        else:
            self._current_agent_id = None

        self._emit("on_agents_changed", self.agents)
        return True

    def _switch_agent(self, direction: int) -> None:
        """Switch to next/previous agent - sends event to controller."""
        self._controller.send(AgentSwitchEvent(direction=direction, source="api"))

    def _switch_agent_internal(self, direction: int) -> None:
        """Internal: Actually switch agent. Called by controller.

        Verifies the target agent is alive before switching.
        If dead, unregisters it and tries the next one.
        """
        if not self._agent_order:
            return

        # Get current index
        current_idx = 0
        if self._current_agent_id and self._current_agent_id in self._agent_order:
            current_idx = self._agent_order.index(self._current_agent_id)

        # Try to find a live agent (circular search, max one full loop)
        tried = 0
        while tried < len(self._agent_order):
            new_idx = (current_idx + direction * (tried + 1)) % len(self._agent_order)
            new_agent_id = self._agent_order[new_idx]
            agent = self._agents.get(new_agent_id)

            if agent:
                # Check if agent is alive (if it has the method)
                if hasattr(agent, "is_alive") and not agent.is_alive():
                    # Agent is dead - unregister and try next
                    self.unregister_agent(new_agent_id)
                    tried += 1
                    continue

                # Agent is alive - switch to it
                self._current_agent_id = new_agent_id
                # Recalculate index after potential unregistrations
                actual_idx = self._agent_order.index(new_agent_id) if new_agent_id in self._agent_order else 0
                self._emit("on_agent_change", self._current_agent_id, actual_idx)
                return

            tried += 1

        # No live agents found
        self._current_agent_id = None

    def _switch_to_agent_by_name(self, name: str) -> bool:
        """Switch to a specific agent by name - sends event to controller."""
        self._controller.send(AgentSwitchEvent(agent_name=name, source="api"))
        return True  # Actual success determined asynchronously

    def _switch_to_agent_by_name_internal(self, name: str) -> bool:
        """Internal: Actually switch by name. Called by controller.

        Verifies the target agent is alive before switching.
        If dead, unregisters it and returns False.
        """
        if not self._agent_order:
            return False

        name_lower = name.lower()

        def try_switch(agent_id: str, idx: int) -> bool:
            """Try to switch to an agent, verify it's alive."""
            agent = self._agents.get(agent_id)
            if not agent:
                return False
            # Check if agent is alive (if it has the method)
            if hasattr(agent, "is_alive") and not agent.is_alive():
                self.unregister_agent(agent_id)
                return False
            self._current_agent_id = agent_id
            # Recalculate index after potential unregistrations
            actual_idx = self._agent_order.index(agent_id) if agent_id in self._agent_order else idx
            self._emit("on_agent_change", agent_id, actual_idx)
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

    def _switch_to_agent_by_index(self, index: int) -> bool:
        """Switch to a specific agent by index (1-based) - sends event."""
        self._controller.send(AgentSwitchEvent(agent_index=index, source="api"))
        return True  # Actual success determined asynchronously

    def _switch_to_agent_by_index_internal(self, index: int) -> bool:
        """Internal: Actually switch by index. Called by controller.

        Verifies the target agent is alive before switching.
        If dead, unregisters it and returns False.
        """
        if not self._agent_order:
            return False

        idx = index - 1  # Convert from 1-based to 0-based
        if idx < 0 or idx >= len(self._agent_order):
            return False

        agent_id = self._agent_order[idx]
        agent = self._agents.get(agent_id)
        if not agent:
            return False

        # Check if agent is alive (if it has the method)
        if hasattr(agent, "is_alive") and not agent.is_alive():
            self.unregister_agent(agent_id)
            return False

        self._current_agent_id = agent_id
        # Recalculate index after potential unregistrations
        actual_idx = self._agent_order.index(agent_id) if agent_id in self._agent_order else idx
        self._emit("on_agent_change", self._current_agent_id, actual_idx)
        return True

    def _send_submit(self) -> None:
        """Send submit (Enter key) to the target."""
        agent = self._get_current_agent()
        if agent:
            # Send empty message with submit flag
            agent.send(create_message("", submit=True))

    def _discard_current(self) -> None:
        """Discard current recording/transcription - sends event."""
        self._controller.send(DiscardCurrentEvent(source="api"))

    def _discard_current_internal(self) -> None:
        """Internal: Actually discard. Called by controller."""
        if self._audio_manager:
            self._audio_manager.clear_queue()
            self._audio_manager.reset_vad()  # Use reset, not flush


    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self, *, start_listening: bool = True) -> None:
        """Start the engine main loop.

        Args:
            start_listening: If True, immediately transition to LISTENING state.
                           If False, stay in OFF state (daemon mode - wait for hotkey/API).
        """
        self._init_vad_components()

        self._running = True
        self._stats_start_time = time.time()

        # Note: Agent registration is handled externally by AgentRegistrar
        # before run() is called. The registrar calls register_agent().

        # Start the state controller (event queue processor)
        self._controller.start()

        try:
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

            # Engine is now ready (STT, VAD, hotkey all initialized)
            self._emit("on_engine_ready")

            # Transition to initial state
            if start_listening:
                old_state = self.state
                self._state_manager.transition(AppState.LISTENING)
                self._emit("on_state_change", old_state, AppState.LISTENING, "start")

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

        # Stop the state controller first
        self._controller.stop()

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

        # Cancel any pending tap timer
        self._tap_detector.reset()

        if self._input_manager:
            self._input_manager.stop()

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
    manual_agents: list[str] | None = None,
    discovery_method: str = "polling",
) -> tuple[VoxtypeEngine, Any, Any]:
    """Create a VoxtypeEngine with appropriate agent registration.

    This is the shared initialization logic used by both CLI (voxtype listen)
    and daemon. Ensures consistent behavior.

    Args:
        config: Application configuration.
        events: Event handler callbacks.
        logger: Optional JSONL logger.
        agent_mode: Override config.output.mode. If None, uses config.
        realtime: Enable realtime transcription. Defaults to False.
        manual_agents: List of agent IDs for manual registration.
                      If None and agent mode, uses auto-discovery.
        discovery_method: Agent discovery method - "polling" or "watchdog".

    Returns:
        Tuple of (engine, registrar, keyboard_agent).
        - registrar: AgentRegistrar if agent mode, None otherwise.
        - keyboard_agent: KeyboardAgent if keyboard mode, None otherwise.
        Caller must call registrar.start() after engine.start() if not None.
    """
    from voxtype.agent.registrar import AutoDiscoveryRegistrar, ManualAgentRegistrar

    # Use overrides or fall back to config/defaults
    effective_agent_mode = agent_mode if agent_mode is not None else (config.output.mode == "agents")
    effective_realtime = realtime if realtime is not None else False  # realtime is CLI-only, default off

    engine = VoxtypeEngine(
        config=config,
        events=events,
        logger=logger,
        agent_mode=effective_agent_mode,
        realtime=effective_realtime,
    )

    registrar: ManualAgentRegistrar | AutoDiscoveryRegistrar | None = None
    keyboard_agent = None
    if effective_agent_mode:
        if manual_agents:
            registrar = ManualAgentRegistrar(engine, manual_agents)
        else:
            registrar = AutoDiscoveryRegistrar(
                engine,
                monitor_type=discovery_method,
            )
    else:
        # Keyboard mode: register KeyboardAgent for local typing
        from voxtype.agent.keyboard import KeyboardAgent

        keyboard_agent = KeyboardAgent(config)
        engine.register_agent(keyboard_agent)

    return engine, registrar, keyboard_agent
