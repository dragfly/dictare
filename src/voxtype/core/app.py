"""Main application orchestrator."""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import TYPE_CHECKING

from rich.console import Console

from voxtype.core.audio_manager import AudioManager
from voxtype.core.state import AppState, ProcessingMode, StateManager
from voxtype.hotkey.base import HotkeyListener
from voxtype.injection.base import TextInjector
from voxtype.stt.base import STTEngine

if TYPE_CHECKING:
    from voxtype.config import Config
    from voxtype.llm import LLMProcessor, LLMResponse
    from voxtype.llm.models import AppState as LLMAppState
    from voxtype.logging.jsonl import JSONLLogger

class VoxtypeApp:
    """Main application orchestrator.

    Coordinates audio capture, STT, hotkey detection, and text injection.
    Uses LLM-first architecture: ALL transcribed text goes through the LLM
    which decides what action to take.
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
        logger: JSONLLogger | None = None,
        output_dir: str | None = None,
        agents: list[str] | None = None,
        realtime: bool = False,
    ) -> None:
        """Initialize the application.

        Args:
            config: Application configuration (all settings read from config).
            logger: Optional JSONL logger for structured logging.
            output_dir: Directory for agent files (<agent>.voxtype).
            agents: List of agent IDs for multi-output mode.
            realtime: Enable realtime transcription feedback while speaking.
        """
        self.config = config
        self._realtime = realtime
        self._partial_text = ""
        self._partial_transcribing = False

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
        self.output_dir = output_dir
        self.agents = agents or []
        self._state_manager = StateManager()
        self._running = False
        self._console = Console()
        self._injection_lock = threading.Lock()  # Lock for text injection
        self._logger = logger

        # Agent state
        self._current_agent_index = 0
        self._input_manager = None  # InputManager for keyboard/device inputs

        # Processing mode: TRANSCRIPTION (fast, no LLM) or COMMAND (LLM)
        self._processing_mode = ProcessingMode(config.command.mode)

        # Listening state: True = actively listening, False = paused
        self._listening = False

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

        # Track if speech was ignored (for ready-to-listen feedback)
        self._speech_was_ignored = False

    @property
    def state(self) -> AppState:
        """Get current application state (read-only, use StateManager for transitions)."""
        return self._state_manager.state

    def _create_stt_engine(self) -> STTEngine:
        """Create and load STT engine."""
        from voxtype.utils.hardware import is_mlx_available

        # Auto-detect MLX on Apple Silicon
        use_mlx = self.config.stt.hw_accel and is_mlx_available()

        if use_mlx:
            from voxtype.stt.mlx_whisper import MLXWhisperEngine
            engine = MLXWhisperEngine()
            device_str = "GPU (MLX/Metal)"
        else:
            from voxtype.stt.faster_whisper import FasterWhisperEngine
            engine = FasterWhisperEngine()
            # Determine device string for display
            if self.config.stt.device == "cuda":
                device_str = "GPU (CUDA)"
            else:
                device_str = "CPU"

        if self.config.verbose:
            self._console.print(f"[dim]Loading STT model {self.config.stt.model_size} on {device_str} (first run may download)...[/]")

        engine.load_model(
            self.config.stt.model_size,
            device=self.config.stt.device,
            compute_type=self.config.stt.compute_type,
            console=self._console,
            verbose=self.config.verbose,
        )

        # Update device string if fallback occurred
        actual_device = getattr(engine, '_device', self.config.stt.device)
        if actual_device != self.config.stt.device:
            self._console.print(f"[dim]Actually using: {actual_device.upper()}[/]")

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

                listener = EvdevHotkeyListener(
                    self.config.hotkey.key,
                    target_device=target_device,
                )

                # Check if key is available, suggest fallback if not
                if not listener.is_key_available():
                    fallback = EvdevHotkeyListener.suggest_fallback_key()
                    if fallback and fallback != self.config.hotkey.key:
                        self._console.print(
                            f"[yellow]Key {self.config.hotkey.key} not found, "
                            f"using {fallback} instead[/]"
                        )
                        listener = EvdevHotkeyListener(
                            fallback,
                            target_device=target_device,
                        )

                return listener
            except ImportError:
                errors.append("evdev not installed (pip install evdev)")
            except Exception as e:
                errors.append(f"evdev error: {e}")

        # Fallback to pynput (macOS and X11)
        try:
            from voxtype.hotkey.pynput_listener import PynputHotkeyListener

            listener = PynputHotkeyListener(self.config.hotkey.key)
            if listener.is_key_available():
                if errors:
                    self._console.print("[yellow]Using pynput for hotkey detection[/]")
                return listener
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

    def _get_current_output_file(self) -> str | None:
        """Get the current output file path based on agent mode."""
        if self.output_dir and self.agents:
            agent = self.agents[self._current_agent_index]
            return f"{self.output_dir}/{agent}.voxtype"
        return None

    def _get_hotwords(self) -> str | None:
        """Build hotwords string from config + wake_word.

        Combines config.stt.hotwords with the wake_word (if set).
        E.g., if config has 'voxtype' and wake_word is 'hey joshua',
        returns 'voxtype,hey joshua'.
        """
        parts = []

        # Add config hotwords
        if self.config.stt.hotwords:
            parts.append(self.config.stt.hotwords)

        # Add wake word (lowercased, normalized)
        if self.trigger_phrase:
            # Normalize: remove punctuation, lowercase
            normalized = self.trigger_phrase.lower().replace(",", " ").strip()
            if normalized and normalized not in parts:
                parts.append(normalized)

        return ",".join(parts) if parts else None

    def _create_injector(self) -> TextInjector:
        """Create text injector based on config.output.method."""
        # Agent output mode (writes to <agent>.voxtype files)
        output_path = self._get_current_output_file()
        if output_path or self.config.output.method == "agent":
            from voxtype.injection.file import FileInjector
            return FileInjector(output_path or "voxtype.txt")

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

    def _init_vad_components(self) -> None:
        """Initialize components for VAD mode."""
        # Always show loading messages - model loading can take 30+ seconds
        self._console.print(f"[dim]Loading STT model ({self.config.stt.model_size})...[/]")

        self._stt = self._create_stt_engine()
        self._injector = self._create_injector()

        # Create audio manager with VAD
        self._console.print()  # Newline after progress bars
        self._audio_manager = AudioManager(
            config=self.config.audio,
            console=self._console,
            verbose=self.config.verbose,
        )
        self._audio_manager.initialize(
            on_speech_start=self._on_vad_speech_start,
            on_speech_end=self._on_vad_speech_end,
            on_max_speech=self._on_max_speech_duration,
            on_partial_audio=self._on_partial_audio if self._realtime else None,
        )

        # Create LLM processor for command mode
        self._init_llm_processor()

        # Create hotkey listener for toggle (if available)
        try:
            self._hotkey = self._create_hotkey_listener()
        except RuntimeError as e:
            if self.config.verbose:
                self._console.print(f"[yellow]Hotkey not available: {e}[/]")
            self._hotkey = None

        if self.config.verbose:
            self._console.print(f"[dim]Injector: {self._injector.get_name()}[/]")
            if self._hotkey:
                self._console.print(f"[dim]Toggle hotkey: {self._hotkey.get_key_name()}[/]")

        # Create agent files and initialize input manager
        self._create_agent_files()
        self._init_input_manager()

        # Pre-initialize audio output for beeps (avoids delay on first beep)
        if self.config.audio.audio_feedback:
            from voxtype.audio.beep import warmup_audio
            warmup_audio()

    def _init_llm_processor(self) -> None:
        """Initialize the LLM-first processor."""
        from voxtype.llm import LLMProcessor

        self._llm_processor = LLMProcessor(
            trigger_phrase=self.trigger_phrase,
            ollama_model=self.config.command.ollama_model,
            ollama_timeout=self.config.command.ollama_timeout,
            console=self._console if self.config.verbose else None,
        )

        # Show which backend is being used
        if self.config.verbose:
            if self._llm_processor._is_ollama_available():
                self._console.print(f"[dim]LLM processor: ollama ({self.config.command.ollama_model})[/]")
            else:
                self._console.print("[dim]LLM processor: keyword fallback[/]")

    def _on_max_speech_duration(self) -> None:
        """Handle max speech duration reached in VAD mode."""
        self._console.print(
            f"[yellow]Max duration ({self.config.audio.max_duration}s) - sending, still listening...[/]"
        )
        # Play beep to notify user
        if self.config.audio.audio_feedback:
            from voxtype.audio.beep import play_beep_sent
            play_beep_sent()

    def _on_vad_speech_start(self) -> None:
        """Handle VAD speech start detection."""
        if self.config.verbose:
            self._console.print(f"[dim][DEBUG] Speech start: state={self.state.name}, listening={self._listening}[/]")

        # Show "Listening:" prefix (aligned with "Transcribed:")
        if self._realtime:
            # Use sys.stdout for proper \r handling (Rich doesn't handle it well)
            import sys
            sys.stdout.write("\033[36m\033[1mListening:\033[0m   ")
            sys.stdout.flush()
        else:
            self._console.print("[bold cyan]Listening...[/]", end="\r")

        # Try to transition IDLE → RECORDING
        if not self._state_manager.try_transition(AppState.RECORDING):
            # Not idle - buffer audio for when we're ready
            if self.config.verbose:
                self._console.print(f"\n[yellow][DEBUG] Speech buffering, state={self.state.name}[/]")
            return

        if self._logger:
            self._logger.log_vad_event("speech_start")

    def _on_partial_audio(self, audio_data) -> None:
        """Handle partial audio during speech for realtime feedback.

        Args:
            audio_data: Accumulated audio data so far.
        """
        if not self._realtime or self._stt is None:
            return

        # Skip if a partial transcription is already running (avoid queue buildup)
        if self._partial_transcribing:
            return

        # Transcribe in background thread to not block VAD
        threading.Thread(
            target=self._transcribe_partial,
            args=(audio_data.copy(),),
            daemon=True,
        ).start()

    def _transcribe_partial(self, audio_data) -> None:
        """Transcribe partial audio and display (background thread)."""
        self._partial_transcribing = True
        try:
            # Use lock to prevent concurrent MLX calls (not thread-safe)
            with self._stt_lock:
                text = self._stt.transcribe(
                    audio_data,
                    language=self.config.stt.language,
                )
            if text and text != self._partial_text:
                self._partial_text = text
                # Clear line and show partial text
                # Use ANSI: \r = start of line, \033[K = clear to end of line
                import sys
                sys.stdout.write(f"\r\033[36m\033[1mListening:\033[0m   \033[2m{text}\033[0m\033[K")
                sys.stdout.flush()
        except Exception:
            pass  # Silently ignore errors on partial transcriptions
        finally:
            self._partial_transcribing = False

    def _on_vad_speech_end(self, audio_data) -> None:
        """Handle VAD speech end detection."""
        # Try to transition to TRANSCRIBING (valid from IDLE or RECORDING)
        if not self._state_manager.try_transition(AppState.TRANSCRIBING):
            # Can't transition - either busy transcribing or in another state
            if self.state == AppState.TRANSCRIBING:
                # Queue audio for later
                if self.config.verbose:
                    self._console.print(f"\n[yellow][DEBUG] Queuing speech (transcribing)[/]")
                self._audio_manager.queue_audio(audio_data)
            return

        # Calculate duration
        sample_rate = self._audio_manager.sample_rate if self._audio_manager else self.config.audio.sample_rate
        duration_ms = len(audio_data) / sample_rate * 1000

        if self._logger:
            self._logger.log_vad_event("speech_end", duration_ms=duration_ms)

        # Check minimum duration
        min_samples = int(sample_rate * self.MIN_RECORDING_DURATION)
        if len(audio_data) < min_samples:
            self._console.print("[dim]Too short, ignoring.        [/]")
            self._state_manager.reset()  # TRANSCRIBING → IDLE
            return

        # Show transcribing status (skip in realtime mode - we'll show Transcribed: instead)
        if not self._realtime:
            self._console.print("[bold yellow]Transcribing...[/]", end="\r")

        # Transcribe and process with LLM
        self._transcribe_and_process(audio_data)

    def _transcribe_and_process(self, audio_data) -> None:
        """Transcribe audio and process with LLM-first architecture."""
        # For realtime mode: move to new line after the "Listening:" line
        if self._realtime:
            import sys
            sys.stdout.write("\n")  # New line after partial text
            sys.stdout.flush()
            self._partial_text = ""

        def do_transcribe():
            try:
                if not self._stt:
                    return

                # Track transcription time (use lock for thread-safety with MLX)
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

                    # Log transcription
                    if self._logger:
                        duration_ms = audio_duration * 1000
                        self._logger.log_transcription(
                            text=text,
                            duration_ms=duration_ms,
                            language=self.config.stt.language,
                        )

                    # Debug mode: always show full transcription
                    if self.config.verbose:
                        self._console.print(f"[blue][DEBUG][/] {text}")

                    # Realtime mode: show final transcription with "Transcribed:" prefix
                    if self._realtime:
                        self._console.print(f"[bold green]Transcribed:[/] {text}")

                    # Check listening state first
                    if not self._listening:
                        # Not listening: ignore transcription
                        self._console.print("[dim]Not listening, ignoring.[/]")
                        return

                    # Listening: check processing mode
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
                else:
                    self._console.print("[dim]No speech detected.                    [/]")
            except Exception as e:
                # Log error
                if self._logger:
                    self._logger.log_error(str(e), context="transcribe_and_process")
                self._console.print(f"[red]Error: {e}[/]")
            finally:
                self._state_manager.reset()  # Return to IDLE
                if self.config.verbose:
                    self._console.print(f"[dim][DEBUG] After transcribe: state={self.state.name}, listening={self._listening}, running={self._running}[/]")
                self._signal_ready_to_listen()
                # Process queued audio if any
                self._process_queued_audio()

        thread = threading.Thread(target=do_transcribe, daemon=True)
        thread.start()

    def _signal_ready_to_listen(self) -> None:
        """Signal ready to listen after transcription (only if speech was ignored)."""
        if not self._speech_was_ignored:
            return

        if not self._listening:
            self._speech_was_ignored = False
            return

        # Delay before ready signal
        time.sleep(0.75)

        self._console.print("[green]Ready to listen[/]")
        if self.config.audio.audio_feedback:
            from voxtype.audio.beep import play_beep_start
            play_beep_start()

        self._speech_was_ignored = False

    def _process_queued_audio(self) -> None:
        """Process any queued audio from speech that occurred during transcription."""
        if not self._audio_manager or not self._audio_manager.has_queued_audio:
            return

        # Pop first queued audio
        audio_data = self._audio_manager.pop_queued_audio()
        if not audio_data:
            return

        if self.config.verbose:
            self._console.print(f"[yellow][DEBUG] Processing queued audio ({self._audio_manager.queued_count} remaining)[/]")

        # Check minimum duration
        sample_rate = self._audio_manager.sample_rate
        min_samples = int(sample_rate * self.MIN_RECORDING_DURATION)
        if len(audio_data) < min_samples:
            self._console.print("[dim]Queued audio too short, ignoring.[/]")
            # Try next in queue
            self._process_queued_audio()
            return

        # Set state and process (IDLE → TRANSCRIBING)
        self._state_manager.transition(AppState.TRANSCRIBING)

        self._console.print("[bold yellow]Transcribing (queued)...[/]", end="\r")
        self._transcribe_and_process(audio_data)

    def _execute_llm_response(self, response: LLMResponse, original_text: str) -> None:
        """Execute the action decided by the LLM.

        Args:
            response: LLM response with action to take.
            original_text: Original transcribed text (for logging).
        """
        from voxtype.llm.models import Action, AppState as LLMAppState, Command

        # Log the LLM decision with full debug info
        if self._logger:
            # Get current LLM processor state for context
            current_llm_state = self._llm_processor.state.value if self._llm_processor else "unknown"
            self._logger.log(
                "llm_decision",
                current_state=current_llm_state,  # State BEFORE this decision
                text=original_text,
                action=response.action.value,
                new_state=response.new_state.value if response.new_state else None,
                command=response.command.value if response.command else None,
                confidence=response.confidence,
                backend=response.backend,
                override_reason=response.override_reason,
                raw_llm_response=response.raw_llm_response,
                text_to_inject=response.text_to_inject,  # Full text for debugging
            )

        if response.action == Action.IGNORE:
            if self.config.verbose or response.user_feedback:
                display = original_text[:50] + "..." if len(original_text) > 50 else original_text
                feedback = response.user_feedback or "No trigger phrase"
                self._console.print(f"[dim]{feedback}:[/] {display}")
            return

        if response.action == Action.CHANGE_STATE:
            if response.new_state == LLMAppState.LISTENING:
                self._enter_listening_mode()
            elif response.new_state == LLMAppState.IDLE:
                self._exit_listening_mode()
            return

        if response.action == Action.EXECUTE:
            self._execute_command(response.command, response.command_args)
            return

        if response.action == Action.INJECT:
            if response.text_to_inject:
                self._state_manager.transition(AppState.INJECTING)
                self._inject_text(response.text_to_inject)

    def _enter_listening_mode(self, trigger: str = "voice_command") -> None:
        """Enter LISTENING mode (continuous transcription without trigger phrase).

        Args:
            trigger: What triggered the state change (voice_command, hotkey_toggle).
        """
        # Play beep FIRST before any console output
        if self.config.audio.audio_feedback:
            from voxtype.audio.beep import play_beep_start
            play_beep_start()

        self._console.print("[bold green]>>> LISTENING MODE[/]")

        if self._logger:
            self._logger.log_state_change(
                old_state="IDLE",
                new_state="LISTENING",
                trigger=trigger,
            )

    def _exit_listening_mode(self, trigger: str = "voice_command") -> None:
        """Exit LISTENING mode.

        Args:
            trigger: What triggered the state change (voice_command, hotkey_toggle).
        """
        # Play beep FIRST before any console output
        if self.config.audio.audio_feedback:
            from voxtype.audio.beep import play_beep_stop
            play_beep_stop()

        self._console.print("[bold yellow]<<< LISTENING MODE OFF[/]")

        if self._logger:
            self._logger.log_state_change(
                old_state="LISTENING",
                new_state="IDLE",
                trigger=trigger,
            )

    def _on_hotkey_toggle(self) -> None:
        """Handle hotkey press in VAD mode.

        Single tap: toggle listening on/off
        Double tap: switch between transcription and command mode
        """
        current_time = time.time()
        time_since_last = current_time - self._last_tap_time
        self._last_tap_time = current_time

        # Double tap detection
        if time_since_last < self.DOUBLE_TAP_THRESHOLD:
            # Cancel pending single tap
            if self._pending_single_tap:
                self._pending_single_tap.cancel()
                self._pending_single_tap = None
            # Double tap: switch processing mode
            self._switch_processing_mode()
            return

        # Schedule single tap with delay to allow for double tap detection
        if self._pending_single_tap:
            self._pending_single_tap.cancel()
        self._pending_single_tap = threading.Timer(
            self.DOUBLE_TAP_THRESHOLD,
            self._toggle_listening
        )
        self._pending_single_tap.start()

    def _toggle_listening(self) -> None:
        """Toggle listening on/off."""
        if self._listening:
            # Turning OFF: disable first, then show message
            self._listening = False
            self._console.print("[bold red]<<< LISTENING OFF[/]")
            self._play_feedback("listening_off")
        else:
            # Turning ON: show message first, then enable
            # This ensures user sees feedback before audio processing starts
            self._console.print("[bold green]>>> LISTENING ON[/]")
            self._play_feedback("listening_on")
            self._listening = True

        # Sync LLM processor state if available
        if self._llm_processor:
            self._llm_processor.set_listening(self._listening)

    def _switch_processing_mode(self) -> None:
        """Switch between transcription and command mode."""
        if self._processing_mode == ProcessingMode.TRANSCRIPTION:
            self._processing_mode = ProcessingMode.COMMAND
            self._console.print("[bold yellow]>>> MODE: COMMAND (LLM)[/]")
        else:
            self._processing_mode = ProcessingMode.TRANSCRIPTION
            self._console.print("[bold cyan]>>> MODE: TRANSCRIPTION (fast)[/]")

        # Sync LLM processor state if available
        if self._llm_processor:
            self._llm_processor.set_listening(self._listening)

        self._speak_mode_with_mute()

    def _load_tts_phrases(self) -> dict:
        """Load TTS phrases from config file or use defaults.

        Default phrases are in English. To customize, create:
        ~/.config/voxtype/tts_phrases.json with structure:
        {
            "transcription_mode": "transcription mode",
            "command_mode": "command mode",
            "agent": "agent",
            "voice": "Samantha"
        }
        """
        import json
        from pathlib import Path

        default_phrases = {
            "transcription_mode": "transcription mode",
            "command_mode": "command mode",
            "agent": "agent",
            "voice": "Samantha",  # macOS voice (Samantha=en, Alice=it)
        }

        phrases_path = Path.home() / ".config" / "voxtype" / "tts_phrases.json"
        if phrases_path.exists():
            try:
                with open(phrases_path) as f:
                    custom = json.load(f)
                # Merge with defaults (custom overrides defaults)
                return {**default_phrases, **custom}
            except Exception:
                pass  # Fall back to defaults on error

        return default_phrases

    def _speak_mode_with_mute(self) -> None:
        """Speak the current mode using TTS, muting mic to avoid self-listening.

        Uses mute_mic_during_feedback config to temporarily disable listening
        while speaking, preventing the TTS from being transcribed.
        """
        if not self.config.audio.audio_feedback:
            return

        import subprocess
        import sys

        mute_mic = self.config.audio.mute_mic_during_feedback
        phrases = self._load_tts_phrases()

        # Get mode phrase from config (default: English)
        if self._processing_mode == ProcessingMode.TRANSCRIPTION:
            text = phrases.get("transcription_mode", "transcription mode")
        else:
            text = phrases.get("command_mode", "command mode")

        voice = phrases.get("voice", "Samantha")

        def _speak():
            # Pause listening if mute_mic enabled
            was_listening = False
            if mute_mic:
                was_listening = self._listening
                if was_listening:
                    self._listening = False

            try:
                if sys.platform == "darwin":
                    subprocess.run(["say", "-v", voice, text], capture_output=True, timeout=10)
                else:
                    # Linux: try espeak-ng, then espeak, then spd-say
                    for cmd in [
                        ["espeak-ng", text],
                        ["espeak", text],
                        ["spd-say", text],
                    ]:
                        try:
                            subprocess.run(cmd, capture_output=True, timeout=5)
                            break
                        except FileNotFoundError:
                            continue
            except Exception:
                pass  # Silently fail if TTS not available
            finally:
                # Resume listening if we paused it
                if mute_mic and was_listening:
                    self._listening = True

        # Always run in background thread to not block keyboard callbacks
        threading.Thread(target=_speak, daemon=True).start()

    def _play_feedback(self, event: str, mode: ProcessingMode | None = None) -> None:
        """Play audio feedback for state changes.

        Args:
            event: Type of event - 'listening_on', 'listening_off'
            mode: Unused (kept for API compatibility)
        """
        if not self.config.audio.audio_feedback:
            return

        try:
            from voxtype.audio.beep import play_beep_start, play_beep_stop

            if event == "listening_on":
                play_beep_start()
            elif event == "listening_off":
                play_beep_stop()
        except Exception:
            pass  # Ignore audio feedback errors

    def _execute_command(self, command: Command | None, args: dict | None) -> None:
        """Execute a voice command.

        Args:
            command: Command to execute.
            args: Optional command arguments.
        """
        from voxtype.llm.models import Command

        if command == Command.REPEAT:
            if self._llm_processor and self._llm_processor.last_injection:
                self._console.print("[cyan]Command: repeat[/]")
                self._inject_text(self._llm_processor.last_injection)
            else:
                self._console.print("[yellow]Nothing to repeat[/]")

    def _inject_text(self, text: str) -> None:
        """Inject text into the terminal.

        Args:
            text: Text to inject.
        """
        # Show transcribed text (skip in realtime mode - already shown with full text)
        if not self._realtime:
            display_text = text[:60] + "..." if len(text) > 60 else text
            self._console.print(f"[green]Transcribed:[/] {display_text}        ")

        # Always add newline (for visual separation or Enter key depending on auto_enter)
        inject_text = text + "\n"

        if self._injector:
            method = self._injector.get_name()
            if self.config.verbose:
                self._console.print(f"[dim]Injecting {len(inject_text)} chars via {method}...[/]")

            # Lock to prevent concurrent injections from multiple threads
            with self._injection_lock:
                inject_start = time.time()
                success = self._injector.type_text(
                    inject_text,
                    delay_ms=self.config.output.typing_delay_ms,
                    auto_enter=self.config.output.auto_enter,
                )
                self._stats_injection_seconds += time.time() - inject_start

                if self.config.verbose:
                    self._console.print(f"[dim]Injection result: {success}[/]")

                # When auto_enter=false, add visual newline for separation between phrases
                if success and not self.config.output.auto_enter:
                    self._injector.send_newline()

            # Beep when file write succeeds (so user knows they can switch project)
            if success and method.startswith("file:"):
                from voxtype.audio.beep import play_beep_sent
                play_beep_sent()

            # Log injection (include enter_sent status if available)
            if self._logger:
                enter_sent = getattr(self._injector, '_enter_sent', None)
                self._logger.log_injection(
                    text=text,
                    method=method,
                    success=success,
                    auto_enter=self.config.output.auto_enter,
                    enter_sent=enter_sent,
                )

            if not success:
                self._console.print("[red]Failed to inject text[/]")

    def run(self, status_panel=None) -> None:
        """Start the application main loop.

        Args:
            status_panel: Optional Rich Panel to display after loading is complete.
        """
        self._run_vad_mode(status_panel=status_panel)

    def _run_vad_mode(self, status_panel=None) -> None:
        """Run in VAD (voice activity detection) mode.

        Args:
            status_panel: Optional Rich Panel to display after loading is complete.
        """
        self._init_vad_components()

        # Show status panel AFTER loading is complete
        if status_panel:
            self._console.print(status_panel)

        self._running = True
        self._stats_start_time = time.time()
        # Note: _listening stays False until we're fully ready

        # Start hotkey listener for toggle (if available)
        if self._hotkey:
            self._hotkey.start(
                on_press=self._on_hotkey_toggle,
                on_release=lambda: None,  # No action on release for toggle mode
            )
            # Show device info (verbose only, evdev only)
            if self.config.verbose and hasattr(self._hotkey, "get_selected_device_info"):
                device_info = self._hotkey.get_selected_device_info()
                if device_info:
                    self._console.print(f"[dim]Hotkey device: {device_info[0]} ({device_info[1]})[/]")

        # IMPORTANT: Show message FIRST, then enable listening, then start streaming
        # This ensures user sees "LISTENING ON" before any audio can be processed
        mode_name = "TRANSCRIPTION" if self._processing_mode == ProcessingMode.TRANSCRIPTION else "COMMAND"
        self._console.print(f"[bold green]>>> LISTENING ON[/] [dim]({mode_name} mode)[/]")

        # Now enable listening and start audio streaming
        self._listening = True
        # Sync LLM processor state
        if self._llm_processor:
            self._llm_processor.set_listening(True)
        if self._audio_manager:
            self._audio_manager.start_streaming(
                is_listening=lambda: self._listening,
                is_running=lambda: self._running,
            )

        # Keep main thread alive, check for device reconnection
        try:
            while self._running:
                time.sleep(0.1)
                if self._audio_manager and self._audio_manager.needs_reconnect():
                    self._console.print("[yellow]Audio device changed, reconnecting...[/]", end="")
                    if not self._audio_manager.reconnect(self._audio_manager._on_audio_chunk):
                        self._console.print(" [red]FAILED[/]")
                        self._console.print("[red]Could not reconnect audio. Please restart.[/]")
                        break
        except KeyboardInterrupt:
            pass

    def _init_input_manager(self) -> None:
        """Initialize input manager for keyboard shortcuts and device profiles."""
        from voxtype.commands.app_commands import AppCommands
        from voxtype.input.manager import InputManager

        # Create app commands handler
        app_commands = AppCommands(self)

        # Create input manager
        self._input_manager = InputManager(
            app_commands=app_commands,
            verbose=self.config.verbose,
        )

        # Load keyboard shortcuts from config
        if self.config.keyboard.shortcuts:
            self._input_manager.load_keyboard_shortcuts(self.config.keyboard.shortcuts)

        # Load device profiles from ~/.config/voxtype/devices/
        self._input_manager.load_device_profiles()

        # Start all input sources
        self._input_manager.start()

        if self.config.verbose and self._input_manager.running_sources:
            self._console.print(f"[dim]Input sources: {', '.join(self._input_manager.running_sources)}[/]")

    def _set_listening(self, on: bool) -> None:
        """Set listening state on/off."""
        if self._listening == on:
            return

        if on:
            # Turning ON: show message first, then enable
            self._console.print("[bold green]>>> LISTENING ON[/]")
            self._play_feedback("listening_on")
            self._listening = True
        else:
            # Turning OFF: disable first, then show message
            self._listening = False
            self._console.print("[bold red]<<< LISTENING OFF[/]")
            self._play_feedback("listening_off")

        # Sync LLM processor state if available
        if self._llm_processor:
            self._llm_processor.set_listening(on)

    def _switch_agent(self, direction: int) -> None:
        """Switch to next/previous agent.

        Args:
            direction: 1 for next, -1 for previous
        """
        if not self.agents:
            return

        # Circular navigation
        self._current_agent_index = (self._current_agent_index + direction) % len(self.agents)
        new_agent = self.agents[self._current_agent_index]

        # Update the injector to write to the new agent file
        self._injector = self._create_injector()

        # Show feedback
        self._console.print(f"[bold cyan]>>> Agent: {new_agent}[/]")

        # Speak the agent name
        self._speak_agent(new_agent)

    def _switch_to_agent_by_name(self, name: str) -> bool:
        """Switch to a specific agent by name.

        Args:
            name: Agent name (case-insensitive, partial match allowed)

        Returns:
            True if agent was found and switched to
        """
        if not self.agents:
            return False

        name_lower = name.lower()

        # Try exact match first
        for i, agent in enumerate(self.agents):
            if agent.lower() == name_lower:
                self._current_agent_index = i
                self._injector = self._create_injector()
                self._console.print(f"[bold cyan]>>> Agent: {agent}[/]")
                self._speak_agent(agent)
                return True

        # Try partial match
        for i, agent in enumerate(self.agents):
            if name_lower in agent.lower():
                self._current_agent_index = i
                self._injector = self._create_injector()
                self._console.print(f"[bold cyan]>>> Agent: {agent}[/]")
                self._speak_agent(agent)
                return True

        self._console.print(f"[yellow]Agent not found: {name}[/]")
        return False

    def _switch_to_agent_by_index(self, index: int) -> bool:
        """Switch to a specific agent by index (1-based).

        Args:
            index: Agent index (1-based, so 1 = first agent)

        Returns:
            True if agent was found and switched to
        """
        if not self.agents:
            return False

        # Convert 1-based to 0-based (silently ignore invalid index)
        idx = index - 1
        if idx < 0 or idx >= len(self.agents):
            return False

        self._current_agent_index = idx
        agent = self.agents[idx]
        self._injector = self._create_injector()
        self._console.print(f"[bold cyan]>>> Agent #{index}: {agent}[/]")
        self._speak_agent(agent)
        return True

    def _repeat_last_injection(self) -> None:
        """Repeat the last injected text."""
        if self._llm_processor and self._llm_processor.last_injection:
            self._console.print("[cyan]Repeat[/]")
            self._inject_text(self._llm_processor.last_injection)
        else:
            self._console.print("[yellow]Nothing to repeat[/]")

    def _speak_agent(self, agent_name: str) -> None:
        """Speak the agent name using TTS.

        If mute_mic_during_feedback is enabled, pauses listening while speaking
        to prevent the microphone from picking up the voice feedback.

        IMPORTANT: Always runs in background thread to avoid blocking keyboard
        callbacks (which could freeze the keyboard with pynput).
        """
        import subprocess
        import sys

        phrases = self._load_tts_phrases()
        agent_prefix = phrases.get("agent", "agent")
        voice = phrases.get("voice", "Samantha")
        text = f"{agent_prefix} {agent_name}"
        mute_mic = self.config.audio.mute_mic_during_feedback

        def _speak():
            # Pause listening if mute_mic enabled (do this in the thread)
            was_listening = False
            if mute_mic:
                was_listening = self._listening
                if was_listening:
                    self._listening = False

            try:
                if sys.platform == "darwin":
                    subprocess.run(["say", "-v", voice, text], capture_output=True, timeout=10)
                else:
                    # Linux: try espeak-ng, then espeak, then spd-say
                    for cmd in [
                        ["espeak-ng", text],
                        ["espeak", text],
                        ["spd-say", "-w", text],
                    ]:
                        try:
                            subprocess.run(cmd, capture_output=True, timeout=5)
                            break
                        except FileNotFoundError:
                            continue
            except Exception:
                pass  # Silently fail if TTS not available
            finally:
                # Resume listening if we paused it
                if mute_mic and was_listening:
                    self._listening = True

        # Always run in background thread - never block keyboard callbacks
        threading.Thread(target=_speak, daemon=True).start()

    def _send_submit(self) -> None:
        """Send submit (Enter key) to the target."""
        if self._injector:
            success = self._injector.send_submit()
            if success:
                self._console.print("[green]Sent[/]")
            else:
                self._console.print("[red]Send failed[/]")

    def _discard_current(self) -> None:
        """Discard current recording/transcription."""
        if self._audio_manager:
            # Clear audio queue
            self._audio_manager.clear_queue()
            # Reset VAD if active
            self._audio_manager.flush_vad()

        # Reset state if recording (RECORDING → IDLE)
        if self.state == AppState.RECORDING:
            self._state_manager.transition(AppState.IDLE)

        self._console.print("[yellow]Discarded[/]")

    def _create_agent_files(self) -> None:
        """Create agent output files (empty, so inputmux can find them)."""
        if not self.output_dir or not self.agents:
            return

        import os
        from pathlib import Path

        # Create output directory if needed
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        for agent in self.agents:
            filepath = f"{self.output_dir}/{agent}.voxtype"
            # Create empty file if doesn't exist
            if not os.path.exists(filepath):
                Path(filepath).touch()
            self._console.print(f"[dim]Output: {filepath}[/]")

    def stop(self) -> None:
        """Stop the application."""
        import gc

        self._running = False
        self._listening = False  # Stop processing new audio immediately

        # Brief pause to let any in-flight audio callbacks complete
        # This prevents race condition where callback tries to use VAD after close
        time.sleep(0.1)

        # Close audio/VAD FIRST to release ONNX resources before anything else
        # This is critical to avoid semaphore leaks on forced shutdown
        if self._audio_manager:
            self._audio_manager.stop_streaming()  # Stop audio callbacks first
            time.sleep(0.05)  # Brief pause for any final callbacks
            self._audio_manager.flush_vad()
            self._audio_manager.close()  # Clean up ONNX resources

        # Force garbage collection to release ONNX semaphores immediately
        gc.collect()

        # Cancel any pending single tap timer
        if self._pending_single_tap:
            self._pending_single_tap.cancel()
            self._pending_single_tap = None

        if self._input_manager:
            self._input_manager.stop()

        if self._hotkey:
            self._hotkey.stop()

        # Show session stats
        self._display_session_stats()

    def _display_session_stats(self) -> None:
        """Display session statistics on exit."""
        import random

        from rich.table import Table

        # Skip if no transcriptions were made
        if self._stats_count == 0:
            return

        # Average typing speed from config (default 40 WPM)
        typing_wpm = self.config.stats.typing_wpm
        chars_per_minute = typing_wpm * 5  # ~200 chars/min at 40 WPM

        # Time it would take to type this text
        typing_time_minutes = self._stats_chars / chars_per_minute
        # Total voxtype time = audio + STT + injection
        total_voxtype_seconds = (
            self._stats_audio_seconds
            + self._stats_transcription_seconds
            + self._stats_injection_seconds
        )
        total_voxtype_minutes = total_voxtype_seconds / 60

        # Effective WPM = words / total minutes
        effective_wpm = self._stats_words / total_voxtype_minutes if total_voxtype_minutes > 0 else 0

        # Time saved = typing time - total voxtype time
        time_saved_minutes = typing_time_minutes - total_voxtype_minutes
        time_saved_seconds = time_saved_minutes * 60

        # Create two-column stats layout
        from rich.columns import Columns

        # Left table: human-friendly stats
        left_table = Table(title="Output", expand=False, show_header=False, box=None)
        left_table.add_column("Metric", style="dim")
        left_table.add_column("Value", style="cyan")
        left_table.add_row("Transcriptions", str(self._stats_count))
        left_table.add_row("Words", str(self._stats_words))
        left_table.add_row("Characters", str(self._stats_chars))
        left_table.add_row("Effective WPM", f"{effective_wpm:.0f}")

        # Right table: technical timing stats
        right_table = Table(title="Timing", expand=False, show_header=False, box=None)
        right_table.add_column("Metric", style="dim")
        right_table.add_column("Value", style="cyan")
        right_table.add_row("Audio", f"{self._stats_audio_seconds:.1f}s")
        right_table.add_row("STT", f"{self._stats_transcription_seconds:.1f}s")
        right_table.add_row("Injection", f"{self._stats_injection_seconds:.1f}s")
        right_table.add_row("Total", f"{total_voxtype_seconds:.1f}s")

        self._console.print()
        self._console.print(Columns([left_table, right_table], padding=(0, 4)))

        # Fun phrases for time saved (shown after the table)
        if time_saved_seconds > 0:
            time_saved_phrases = [
                "Saved you [bold]{time}[/]. You're welcome.",
                "[bold]{time}[/] back in your pocket.",
                "Time saved: [bold]{time}[/]. My pleasure!",
                "[bold]{time}[/] extra for coffee.",
                "[bold]{time}[/] gained. Use them wisely!",
                "[bold]{time}[/] freed up. Maybe call someone who'd love to hear from you?",
                "[bold]{time}[/] saved. Pay it forward.",
                "[bold]{time}[/] reclaimed. Go make someone's day.",
                "[bold]{time}[/] in your hands. Spend them on something that matters.",
                "[bold]{time}[/] unlocked. Perfect for a random act of kindness.",
            ]

            # Format time saved
            if time_saved_seconds >= 60:
                time_str = f"{time_saved_minutes:.1f} minutes"
            else:
                time_str = f"{time_saved_seconds:.0f} seconds"

            # Pick random phrase and display
            phrase = random.choice(time_saved_phrases).format(time=time_str)
            self._console.print()
            self._console.print(f"[green bold]✨ {phrase} ✨[/]")
            self._console.print()
