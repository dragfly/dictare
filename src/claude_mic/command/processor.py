"""Command processor - executes voice commands."""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING, Callable, Optional

from rich.console import Console

from claude_mic.command.base import (
    CommandIntent,
    CommandResult,
    IntentClassifier,
)
from claude_mic.command.keyword import KeywordClassifier
from claude_mic.command.ollama import OllamaClassifier

if TYPE_CHECKING:
    from claude_mic.injection.base import TextInjector
    from claude_mic.window.base import WindowManager


class CommandProcessor:
    """Processes voice commands and executes actions.

    Handles command classification, execution, and state transitions.
    """

    def __init__(
        self,
        injector: TextInjector,
        classifier: Optional[IntentClassifier] = None,
        window_manager: Optional[WindowManager] = None,
        on_enter_listening: Optional[Callable[[], None]] = None,
        on_exit_listening: Optional[Callable[[], None]] = None,
        console: Optional[Console] = None,
        ollama_model: str = "llama3.2:1b",
        ollama_timeout: float = 5.0,
        format_text: bool = True,
    ) -> None:
        """Initialize command processor.

        Args:
            injector: Text injector for paste operations.
            classifier: Intent classifier (auto-detected if None).
            window_manager: Optional window manager for target window commands.
            on_enter_listening: Callback when entering LISTENING mode.
            on_exit_listening: Callback when exiting LISTENING mode.
            console: Rich console for output.
            ollama_model: Ollama model to use.
            ollama_timeout: Ollama request timeout.
            format_text: Whether to format text via LLM.
        """
        self._injector = injector
        self._window_manager = window_manager
        self._console = console or Console()
        self._on_enter_listening = on_enter_listening
        self._on_exit_listening = on_exit_listening

        # History for undo/repeat
        self._last_injection: Optional[str] = None
        self._history: list[str] = []

        # Initialize classifier with fallback chain
        if classifier:
            self._classifier = classifier
        else:
            keyword_fallback = KeywordClassifier()
            ollama = OllamaClassifier(
                model=ollama_model,
                timeout=ollama_timeout,
                fallback=keyword_fallback,
                format_text=format_text,
            )
            self._classifier = ollama if ollama.is_available() else keyword_fallback

        if self._console:
            self._console.print(f"[dim]Command classifier: {self._classifier.get_name()}[/]")

    def process(self, text: str) -> tuple[bool, Optional[str]]:
        """Process a voice command.

        Args:
            text: Transcribed text (wake word already removed).

        Returns:
            Tuple of (was_command, formatted_text).
            - was_command: True if command was handled, False if text should be injected.
            - formatted_text: LLM-formatted text if available.
        """
        result = self._classifier.classify(text)

        handlers = {
            CommandIntent.ASCOLTA: self._handle_ascolta,
            CommandIntent.SMETTI: self._handle_smetti,
            CommandIntent.INCOLLA: self._handle_incolla,
            CommandIntent.ANNULLA: self._handle_annulla,
            CommandIntent.RIPETI: self._handle_ripeti,
            CommandIntent.TARGET_WINDOW: self._handle_target_window,
            CommandIntent.TEXT: self._handle_text,
            CommandIntent.UNKNOWN: self._handle_unknown,
        }

        handler = handlers.get(result.intent, self._handle_unknown)
        was_command = handler(result)

        # Return formatted text for TEXT intent
        formatted = result.formatted_text if result.intent == CommandIntent.TEXT else None
        return was_command, formatted

    def _handle_ascolta(self, result: CommandResult) -> bool:
        """Enter LISTENING mode."""
        self._console.print("[bold cyan]>>> Entering LISTENING mode[/]")
        self._console.print("[dim]Speak freely - say 'smetti' or 'Joshua smetti' to exit[/]")
        if self._on_enter_listening:
            self._on_enter_listening()
        return True

    def _handle_smetti(self, result: CommandResult) -> bool:
        """Exit LISTENING mode."""
        self._console.print("[bold yellow]<<< Exiting LISTENING mode[/]")
        if self._on_exit_listening:
            self._on_exit_listening()
        return True

    def _handle_incolla(self, result: CommandResult) -> bool:
        """Paste from clipboard."""
        self._console.print("[dim]Incollando dalla clipboard...[/]")
        try:
            self._send_paste()
            return True
        except Exception as e:
            self._console.print(f"[red]Paste failed: {e}[/]")
        return True

    def _handle_annulla(self, result: CommandResult) -> bool:
        """Undo last injection (Ctrl+Z)."""
        self._console.print("[dim]Annullando...[/]")
        try:
            self._send_undo()
            return True
        except Exception as e:
            self._console.print(f"[red]Undo failed: {e}[/]")
        return True

    def _handle_ripeti(self, result: CommandResult) -> bool:
        """Repeat last transcription."""
        if self._last_injection:
            display = self._last_injection[:40] + "..." if len(self._last_injection) > 40 else self._last_injection
            self._console.print(f"[dim]Ripetendo: {display}[/]")
            self._injector.type_text(self._last_injection)
        else:
            self._console.print("[yellow]Niente da ripetere[/]")
        return True

    def _handle_target_window(self, result: CommandResult) -> bool:
        """Change target window."""
        if not self._window_manager:
            self._console.print("[yellow]Window manager non disponibile[/]")
            return True

        query = result.target_query
        if not query:
            self._console.print("[yellow]Nessuna finestra specificata[/]")
            return True

        windows = self._window_manager.find_windows(query)

        if not windows:
            self._console.print(f"[yellow]Nessuna finestra trovata per '{query}'[/]")
            return True

        if len(windows) == 1:
            self._window_manager.set_target(windows[0])
            self._console.print(f"[green]Target: {windows[0].name}[/]")
        else:
            # Multiple matches - show options
            self._console.print("[yellow]Ho trovato più finestre:[/]")
            for i, win in enumerate(windows[:5], 1):
                self._console.print(f"  {i}. {win.name}")
            self._console.print("[dim]Specifica meglio quale vuoi[/]")

        return True

    def _handle_text(self, result: CommandResult) -> bool:
        """Regular text - should be injected."""
        # Store for repeat functionality
        text = result.formatted_text or result.original_text
        if text:
            self._last_injection = text
            self._history.append(text)
            if len(self._history) > 10:
                self._history.pop(0)
        return False  # Let caller handle injection

    def _handle_unknown(self, result: CommandResult) -> bool:
        """Unknown intent - treat as text."""
        self._console.print("[dim]Comando non riconosciuto, trattato come testo[/]")
        return False

    def _send_paste(self) -> None:
        """Send Ctrl+V paste shortcut."""
        ydotool = shutil.which("ydotool")
        if ydotool:
            # Ctrl+V using ydotool (key codes: 29=Ctrl, 47=V)
            subprocess.run(
                [ydotool, "key", "29:1", "47:1", "47:0", "29:0"],
                capture_output=True,
                timeout=5,
            )
            return

        xdotool = shutil.which("xdotool")
        if xdotool:
            subprocess.run(
                [xdotool, "key", "ctrl+v"],
                capture_output=True,
                timeout=5,
            )
            return

    def _send_undo(self) -> None:
        """Send Ctrl+Z undo shortcut."""
        ydotool = shutil.which("ydotool")
        if ydotool:
            # Ctrl+Z using ydotool (key codes: 29=Ctrl, 44=Z)
            subprocess.run(
                [ydotool, "key", "29:1", "44:1", "44:0", "29:0"],
                capture_output=True,
                timeout=5,
            )
            return

        xdotool = shutil.which("xdotool")
        if xdotool:
            subprocess.run(
                [xdotool, "key", "ctrl+z"],
                capture_output=True,
                timeout=5,
            )
            return

    def record_injection(self, text: str) -> None:
        """Record an injection for repeat functionality.

        Args:
            text: Text that was injected.
        """
        self._last_injection = text
        self._history.append(text)
        if len(self._history) > 10:
            self._history.pop(0)

    def get_classifier_name(self) -> str:
        """Get the name of the active classifier."""
        return self._classifier.get_name()
