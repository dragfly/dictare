"""Main application orchestrator."""

from __future__ import annotations

import sys
import threading
import time
from typing import TYPE_CHECKING

from rich.console import Console

from claude_mic.audio.capture import AudioCapture
from claude_mic.core.state import AppState
from claude_mic.hotkey.base import HotkeyListener
from claude_mic.injection.base import TextInjector
from claude_mic.stt.base import STTEngine

if TYPE_CHECKING:
    from claude_mic.audio.vad import SileroVAD, StreamingVAD
    from claude_mic.config import Config

class ClaudeMicApp:
    """Main application orchestrator.

    Coordinates audio capture, STT, hotkey detection, and text injection.
    Supports both push-to-talk and VAD (voice activity detection) modes.
    """

    # Minimum recording duration in seconds
    MIN_RECORDING_DURATION = 0.3

    def __init__(
        self,
        config: Config,
        use_vad: bool = False,
        vad_silence_ms: int | None = None,
        wake_word: str | None = None,
        debug: bool = False,
    ) -> None:
        """Initialize the application.

        Args:
            config: Application configuration.
            use_vad: If True, use VAD mode instead of push-to-talk.
            vad_silence_ms: Silence duration in ms to end speech (default 1200).
            wake_word: Optional wake word to activate (e.g., "Joshua").
            debug: If True, show all transcriptions but only paste with wake word.
        """
        self.config = config
        self.use_vad = use_vad
        self.vad_silence_ms = vad_silence_ms or 1200
        self.wake_word = wake_word.lower() if wake_word else None
        self.debug = debug
        self.state = AppState.IDLE
        self._running = False
        self._console = Console()
        self._lock = threading.Lock()

        # Initialize components
        self._audio: AudioCapture | None = None
        self._stt: STTEngine | None = None
        self._hotkey: HotkeyListener | None = None
        self._injector: TextInjector | None = None
        self._recording_timer: threading.Timer | None = None

        # VAD components
        self._vad: SileroVAD | None = None
        self._streaming_vad: StreamingVAD | None = None

    def _create_audio_capture(self) -> AudioCapture:
        """Create audio capture component."""
        return AudioCapture(
            sample_rate=self.config.audio.sample_rate,
            channels=self.config.audio.channels,
            device=self.config.audio.device,
        )

    def _create_stt_engine(self) -> STTEngine:
        """Create and load STT engine."""
        if self.config.stt.backend == "faster-whisper":
            from claude_mic.stt.faster_whisper import FasterWhisperEngine

            engine = FasterWhisperEngine()
        else:
            raise ValueError(f"Unknown STT backend: {self.config.stt.backend}")

        device_str = "GPU (CUDA)" if self.config.stt.device == "cuda" else "CPU"
        if self.config.verbose:
            self._console.print(f"[dim]Loading {self.config.stt.model_size} model on {device_str}...[/]")

        engine.load_model(
            self.config.stt.model_size,
            device=self.config.stt.device,
            compute_type=self.config.stt.compute_type,
        )

        if self.config.verbose:
            self._console.print("[dim]Model loaded.[/]")

        return engine

    def _create_hotkey_listener(self) -> HotkeyListener:
        """Create hotkey listener with smart fallback."""
        backend = self.config.hotkey.backend
        errors: list[str] = []

        # Try evdev first on Linux
        if backend in ("auto", "evdev") and sys.platform == "linux":
            try:
                from claude_mic.hotkey.evdev_listener import EvdevHotkeyListener

                listener = EvdevHotkeyListener(self.config.hotkey.key)

                # Check if key is available, suggest fallback if not
                if not listener.is_key_available():
                    fallback = EvdevHotkeyListener.suggest_fallback_key()
                    if fallback and fallback != self.config.hotkey.key:
                        self._console.print(
                            f"[yellow]Key {self.config.hotkey.key} not found, "
                            f"using {fallback} instead[/]"
                        )
                        listener = EvdevHotkeyListener(fallback)

                return listener
            except ImportError:
                errors.append("evdev not installed (pip install evdev)")
            except Exception as e:
                errors.append(f"evdev error: {e}")

        # Fallback to pynput
        if backend in ("auto", "pynput"):
            try:
                from claude_mic.hotkey.pynput_listener import PynputHotkeyListener

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

    def _create_injector(self) -> TextInjector:
        """Create text injector with auto-detection."""
        import sys

        from claude_mic.injection.clipboard import ClipboardInjector

        # Platform-specific imports
        if sys.platform == "darwin":
            from claude_mic.injection.macos import MacOSInjector
        else:
            from claude_mic.injection.wtype import WtypeInjector
            from claude_mic.injection.xdotool import XdotoolInjector
            from claude_mic.injection.ydotool import YdotoolInjector

        backend = self.config.injection.backend

        if backend != "auto":
            # Use specific backend
            if sys.platform == "darwin":
                injectors = {
                    "macos": MacOSInjector,
                    "clipboard": ClipboardInjector,
                }
            else:
                injectors = {
                    "ydotool": YdotoolInjector,
                    "wtype": WtypeInjector,
                    "xdotool": XdotoolInjector,
                    "clipboard": ClipboardInjector,
                }
            if backend in injectors:
                injector = injectors[backend]()
                if injector.is_available():
                    return injector
                self._console.print(f"[yellow]{backend} not available[/]")

        # Auto-detect best available injector
        if sys.platform == "darwin":
            candidates = [
                MacOSInjector(),
                ClipboardInjector(),
            ]
        else:
            candidates = [
                YdotoolInjector(),
                WtypeInjector(),
                XdotoolInjector(),
                ClipboardInjector(),
            ]

        for injector in candidates:
            if injector.is_available():
                if isinstance(injector, ClipboardInjector):
                    self._console.print(
                        "[yellow]Using clipboard mode. "
                        "Press Ctrl+V to paste after speaking.[/]"
                    )
                return injector

        # Last resort: return clipboard even if not available
        # (will fail gracefully on use)
        return ClipboardInjector()

    def _init_components(self) -> None:
        """Initialize all components for push-to-talk mode."""
        self._console.print("[dim]Initializing components...[/]")

        self._audio = self._create_audio_capture()
        self._stt = self._create_stt_engine()
        self._hotkey = self._create_hotkey_listener()
        self._injector = self._create_injector()

        if self.config.verbose:
            self._console.print(f"[dim]Hotkey: {self._hotkey.get_key_name()}[/]")
            self._console.print(f"[dim]Injector: {self._injector.get_name()}[/]")

        self._console.print(f"[green]Ready![/] Press {self.config.hotkey.key} to record.")

    def _init_vad_components(self) -> None:
        """Initialize components for VAD mode."""
        self._console.print("[dim]Initializing VAD components...[/]")

        self._audio = self._create_audio_capture()
        self._stt = self._create_stt_engine()
        self._injector = self._create_injector()

        # Create VAD
        from claude_mic.audio.vad import SileroVAD, StreamingVAD

        self._vad = SileroVAD(
            threshold=0.5,
            neg_threshold=0.35,
            min_silence_ms=self.vad_silence_ms,  # End speech after silence
            min_speech_ms=250,   # Need 250ms speech to trigger
            sample_rate=self.config.audio.sample_rate,
        )

        # Create streaming VAD processor
        self._streaming_vad = StreamingVAD(
            vad=self._vad,
            on_speech_start=self._on_vad_speech_start,
            on_speech_end=self._on_vad_speech_end,
        )

        if self.config.verbose:
            self._console.print(f"[dim]Injector: {self._injector.get_name()}[/]")

        self._console.print("[green]Ready![/] Start speaking...")

    def _on_hotkey_press(self) -> None:
        """Handle hotkey press - start recording."""
        with self._lock:
            if self.state != AppState.IDLE:
                return

            self.state = AppState.RECORDING
            if self._audio:
                self._audio.start_recording()

            # Start max duration timer
            max_dur = self.config.audio.max_duration
            if max_dur > 0:
                self._recording_timer = threading.Timer(max_dur, self._on_max_duration)
                self._recording_timer.start()

            self._console.print("[bold cyan]Recording...[/]", end="\r")

    def _on_max_duration(self) -> None:
        """Handle max recording duration reached."""
        self._console.print(f"[yellow]Max duration ({self.config.audio.max_duration}s) reached[/]")
        self._on_hotkey_release()

    def _on_hotkey_release(self) -> None:
        """Handle hotkey release - stop recording and transcribe."""
        # Cancel max duration timer
        if self._recording_timer:
            self._recording_timer.cancel()
            self._recording_timer = None

        with self._lock:
            if self.state != AppState.RECORDING:
                return

            self.state = AppState.TRANSCRIBING

        if not self._audio:
            self.state = AppState.IDLE
            return

        audio_data = self._audio.stop_recording()

        # Check minimum duration
        min_samples = int(self.config.audio.sample_rate * self.MIN_RECORDING_DURATION)
        if len(audio_data) < min_samples:
            self._console.print("[dim]Recording too short, ignoring.        [/]")
            self.state = AppState.IDLE
            return

        self._console.print("[bold yellow]Transcribing...[/]", end="\r")

        # Transcribe in background to not block hotkey listener
        def transcribe_and_inject() -> None:
            try:
                if not self._stt:
                    return

                text = self._stt.transcribe(
                    audio_data,
                    language=self.config.stt.language,
                )

                if text:
                    with self._lock:
                        self.state = AppState.INJECTING

                    # Truncate display if too long
                    display_text = text[:60] + "..." if len(text) > 60 else text
                    self._console.print(f"[green]Transcribed:[/] {display_text}        ")

                    # Add Enter if configured
                    inject_text = text + "\n" if self.config.injection.auto_enter else text

                    if self._injector:
                        # Pass auto_paste for clipboard mode
                        if self._injector.get_name() == "clipboard":
                            success = self._injector.type_text(
                                inject_text,
                                delay_ms=self.config.injection.typing_delay_ms,
                                auto_paste=self.config.injection.auto_paste,
                            )
                            if success and self.config.injection.auto_paste:
                                pass  # Auto-pasted, no message needed
                            elif success:
                                self._console.print(
                                    "[yellow]Copied to clipboard (Ctrl+V to paste)[/]"
                                )
                        else:
                            success = self._injector.type_text(
                                inject_text,
                                delay_ms=self.config.injection.typing_delay_ms,
                            )

                        if not success:
                            if self.config.injection.fallback_to_clipboard:
                                # Try clipboard fallback
                                from claude_mic.injection.clipboard import ClipboardInjector

                                clipboard = ClipboardInjector()
                                if clipboard.is_available():
                                    clipboard.type_text(text)
                                    self._console.print(
                                        "[yellow]Copied to clipboard (Ctrl+V to paste)[/]"
                                    )
                            else:
                                self._console.print("[red]Failed to inject text[/]")
                else:
                    self._console.print("[dim]No speech detected.                    [/]")
            except Exception as e:
                self._console.print(f"[red]Error: {e}[/]")
            finally:
                self.state = AppState.IDLE

        thread = threading.Thread(target=transcribe_and_inject, daemon=True)
        thread.start()

    def _on_vad_speech_start(self) -> None:
        """Handle VAD speech start detection."""
        with self._lock:
            if self.state != AppState.IDLE:
                # Debug: show why we're ignoring
                if self.debug:
                    self._console.print(f"[yellow][DEBUG] Speech ignored, state={self.state.name}[/]")
                return
            self.state = AppState.RECORDING

        self._console.print("[bold cyan]Listening...[/]", end="\r")

    def _on_vad_speech_end(self, audio_data) -> None:
        """Handle VAD speech end detection."""
        import numpy as np

        with self._lock:
            if self.state != AppState.RECORDING:
                return
            self.state = AppState.TRANSCRIBING

        # Check minimum duration
        min_samples = int(self.config.audio.sample_rate * self.MIN_RECORDING_DURATION)
        if len(audio_data) < min_samples:
            self._console.print("[dim]Too short, ignoring.        [/]")
            self.state = AppState.IDLE
            return

        self._console.print("[bold yellow]Transcribing...[/]", end="\r")

        # Transcribe and inject
        self._transcribe_and_inject(audio_data)

    def _check_wake_word(self, text: str) -> tuple[bool, str]:
        """Check if text starts with wake word and return filtered text.

        Args:
            text: Transcribed text.

        Returns:
            Tuple of (wake_word_found, filtered_text).
        """
        if not self.wake_word:
            return True, text

        text_lower = text.lower().strip()

        if self.debug:
            self._console.print(f"[blue][DEBUG] Wake check: text_lower='{text_lower}'[/]")
            self._console.print(f"[blue][DEBUG] Wake word='{self.wake_word}'[/]")

        # Check various formats: "Joshua, ...", "Joshua ...", "Joshua:", "Joshua."
        for sep in [",", ":", ".", " "]:
            pattern = self.wake_word + sep
            if text_lower.startswith(pattern):
                # Remove wake word and separator
                filtered = text[len(self.wake_word) + 1:].strip()
                if self.debug:
                    self._console.print(f"[blue][DEBUG] Match with '{sep}' -> filtered='{filtered}'[/]")
                return True, filtered

        # Check if it starts exactly with wake word (might be all they said)
        if text_lower.startswith(self.wake_word):
            filtered = text[len(self.wake_word):].strip()
            if self.debug:
                self._console.print(f"[blue][DEBUG] Exact match -> filtered='{filtered}'[/]")
            if filtered:
                return True, filtered

        if self.debug:
            self._console.print(f"[blue][DEBUG] No match found[/]")
        return False, text

    def _transcribe_and_inject(self, audio_data) -> None:
        """Transcribe audio and inject text."""
        def do_transcribe():
            try:
                if not self._stt:
                    return

                text = self._stt.transcribe(
                    audio_data,
                    language=self.config.stt.language,
                )

                if text:
                    # Debug mode: always show full transcription
                    if self.debug:
                        self._console.print(f"[blue][DEBUG][/] {text}")

                    # Check wake word
                    wake_found, filtered_text = self._check_wake_word(text)
                    if not wake_found:
                        # Show what was heard (so user understands)
                        if not self.debug:  # Already shown in debug mode
                            display = text[:50] + "..." if len(text) > 50 else text
                            self._console.print(f"[dim]No wake word:[/] {display}")
                        self.state = AppState.IDLE
                        return

                    text = filtered_text
                    if not text:
                        self._console.print("[dim]Wake word only, no command.[/]")
                        self.state = AppState.IDLE
                        return
                    with self._lock:
                        self.state = AppState.INJECTING

                    # Truncate display if too long
                    display_text = text[:60] + "..." if len(text) > 60 else text
                    self._console.print(f"[green]Transcribed:[/] {display_text}        ")

                    # Add Enter if configured
                    inject_text = text + "\n" if self.config.injection.auto_enter else text

                    if self._injector:
                        # Pass auto_paste for clipboard mode
                        if self._injector.get_name() == "clipboard":
                            success = self._injector.type_text(
                                inject_text,
                                delay_ms=self.config.injection.typing_delay_ms,
                                auto_paste=self.config.injection.auto_paste,
                            )
                            if success and self.config.injection.auto_paste:
                                pass  # Auto-pasted, no message needed
                            elif success:
                                self._console.print(
                                    "[yellow]Copied to clipboard (Ctrl+V to paste)[/]"
                                )
                        else:
                            success = self._injector.type_text(
                                inject_text,
                                delay_ms=self.config.injection.typing_delay_ms,
                            )

                        if not success:
                            if self.config.injection.fallback_to_clipboard:
                                from claude_mic.injection.clipboard import ClipboardInjector

                                clipboard = ClipboardInjector()
                                if clipboard.is_available():
                                    clipboard.type_text(text)
                                    self._console.print(
                                        "[yellow]Copied to clipboard (Ctrl+V to paste)[/]"
                                    )
                            else:
                                self._console.print("[red]Failed to inject text[/]")
                else:
                    self._console.print("[dim]No speech detected.                    [/]")
            except Exception as e:
                self._console.print(f"[red]Error: {e}[/]")
            finally:
                self.state = AppState.IDLE

        thread = threading.Thread(target=do_transcribe, daemon=True)
        thread.start()

    def _on_vad_audio_chunk(self, chunk) -> None:
        """Process audio chunk through VAD."""
        if self._streaming_vad and self._running:
            self._streaming_vad.process_chunk(chunk)

    def run(self) -> None:
        """Start the application main loop."""
        if self.use_vad:
            self._run_vad_mode()
        else:
            self._run_push_to_talk_mode()

    def _run_push_to_talk_mode(self) -> None:
        """Run in push-to-talk mode."""
        self._init_components()
        self._running = True

        if self._hotkey:
            self._hotkey.start(
                on_press=self._on_hotkey_press,
                on_release=self._on_hotkey_release,
            )

        # Keep main thread alive
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass

    def _run_vad_mode(self) -> None:
        """Run in VAD (voice activity detection) mode."""
        self._init_vad_components()
        self._running = True

        # Start continuous audio streaming
        if self._audio:
            self._audio.start_streaming(self._on_vad_audio_chunk)

        # Keep main thread alive
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass

    def stop(self) -> None:
        """Stop the application."""
        self._running = False

        if self._hotkey:
            self._hotkey.stop()

        if self._audio:
            if self._audio.is_recording():
                self._audio.stop_recording()
            self._audio.stop_streaming()

        if self._streaming_vad:
            self._streaming_vad.flush()
