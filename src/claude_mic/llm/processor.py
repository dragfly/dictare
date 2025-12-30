"""Unified LLM processor - ALL decisions go through here."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from claude_mic.llm.models import Action, AppState, Command, LLMRequest, LLMResponse
from claude_mic.llm.prompts import (
    FALLBACK_ENTER_KEYWORDS,
    FALLBACK_EXIT_KEYWORDS,
    FALLBACK_PASTE_KEYWORDS,
    FALLBACK_REPEAT_KEYWORDS,
    FALLBACK_TARGET_ACTIVE_KEYWORDS,
    FALLBACK_UNDO_KEYWORDS,
    build_system_prompt,
    build_user_prompt,
)

if TYPE_CHECKING:
    from rich.console import Console

class LLMProcessor:
    """Unified LLM processor - ALL decisions go through here.

    This processor handles:
    - Trigger phrase detection (anywhere in the text)
    - Command classification
    - State management (IDLE ↔ LISTENING)
    - Text formatting for injection
    """

    def __init__(
        self,
        trigger_phrase: str | None = None,
        ollama_model: str = "llama3.2:1b",
        ollama_timeout: float = 5.0,
        console: Console | None = None,
    ) -> None:
        """Initialize the LLM processor.

        Args:
            trigger_phrase: Trigger phrase to activate (e.g., "Joshua").
            ollama_model: Ollama model to use.
            ollama_timeout: Timeout for Ollama requests.
            console: Console for debug output.
        """
        self.trigger_phrase = trigger_phrase.lower() if trigger_phrase else None
        self.ollama_model = ollama_model
        self.ollama_timeout = ollama_timeout
        self._console = console
        self._state = AppState.IDLE
        self._history: list[str] = []
        self._last_injection: str | None = None
        self._ollama_available: bool | None = None

    @property
    def state(self) -> AppState:
        """Current application state."""
        return self._state

    @property
    def last_injection(self) -> str | None:
        """Last injected text (for repeat command)."""
        return self._last_injection

    def process(self, text: str) -> LLMResponse:
        """Process transcribed text and return action.

        This is the main entry point. ALL transcribed text goes through here.

        Args:
            text: Transcribed text from STT.

        Returns:
            LLMResponse with the action to take.
        """
        request = LLMRequest(
            text=text,
            current_state=self._state,
            trigger_phrase=self.trigger_phrase,
            history=self._history[-5:],
        )

        # Try Ollama first, fall back to keyword matching
        if self._is_ollama_available():
            response = self._process_with_ollama(request)
        else:
            response = self._process_with_keywords(request)

        # Update internal state
        if response.action == Action.CHANGE_STATE and response.new_state:
            self._state = response.new_state

        if response.action == Action.INJECT and response.text_to_inject:
            self._last_injection = response.text_to_inject

        self._history.append(text)

        return response

    def _is_ollama_available(self) -> bool:
        """Check if Ollama is available."""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                timeout=2.0,
            )
            self._ollama_available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._ollama_available = False

        if self._console and not self._ollama_available:
            self._console.print("[yellow]Ollama not available, using keyword fallback[/]")

        return self._ollama_available

    def _process_with_ollama(self, request: LLMRequest) -> LLMResponse:
        """Process with Ollama LLM."""
        system_prompt = build_system_prompt(request)
        user_prompt = build_user_prompt(request)

        try:
            result = subprocess.run(
                [
                    "ollama", "run", self.ollama_model,
                    "--format", "json",
                    f"{system_prompt}\n\n{user_prompt}",
                ],
                capture_output=True,
                text=True,
                timeout=self.ollama_timeout,
            )

            if result.returncode != 0:
                return self._process_with_keywords(request)

            return self._parse_ollama_response(result.stdout.strip(), request)

        except subprocess.TimeoutExpired:
            if self._console:
                self._console.print("[yellow]Ollama timeout, using keywords[/]")
            response = self._process_with_keywords(request)
            response.override_reason = f"Ollama timeout ({self.ollama_timeout}s)"
            return response
        except Exception as e:
            if self._console:
                self._console.print(f"[yellow]Ollama error: {e}[/]")
            response = self._process_with_keywords(request)
            response.override_reason = f"Ollama error: {e}"
            return response

    def _parse_ollama_response(self, response_text: str, request: LLMRequest) -> LLMResponse:
        """Parse Ollama JSON response into LLMResponse."""
        try:
            data = json.loads(response_text)

            action = Action(data.get("action", "ignore"))

            new_state = None
            if data.get("new_state"):
                new_state = AppState(data["new_state"])

            command = None
            if data.get("command"):
                command = Command(data["command"])

            # Sanity check: if action is change_state but new_state is None, fall back to keywords
            if action == Action.CHANGE_STATE and new_state is None:
                if self._console:
                    self._console.print("[yellow]LLM returned change_state without new_state, using keywords[/]")
                return self._process_with_keywords(request)

            # Sanity check: if action is execute but command is None, fall back
            if action == Action.EXECUTE and command is None:
                if self._console:
                    self._console.print("[yellow]LLM returned execute without command, using keywords[/]")
                return self._process_with_keywords(request)

            # In LISTENING mode: check for exit commands first, then handle LLM decision
            if request.current_state == AppState.LISTENING:
                text_lower = request.text.lower()
                words = text_lower.split()

                # Block invalid transition: can't enter LISTENING when already in LISTENING
                if action == Action.CHANGE_STATE and new_state == AppState.LISTENING:
                    if self._console:
                        self._console.print("[yellow]LISTENING: LLM tried to re-enter LISTENING, injecting instead[/]")
                    return LLMResponse.inject(
                        request.text,
                        backend="ollama",
                        override="Invalid state transition: already in LISTENING",
                    )

                # Check for SHORT exit commands (≤4 words) - these should always exit
                # Examples: "smetti", "stop", "Joshua smetti", "ok basta"
                if len(words) <= 4:
                    for keyword in FALLBACK_EXIT_KEYWORDS:
                        if keyword in text_lower:
                            if self._console:
                                self._console.print(f"[yellow]LISTENING: short exit command '{keyword}' detected[/]")
                            return LLMResponse.exit_listening(backend="ollama")

                # If LLM says IGNORE on longer text, inject anyway
                if action == Action.IGNORE:
                    if self._console:
                        self._console.print("[yellow]LISTENING: LLM said ignore, injecting anyway[/]")
                    return LLMResponse.inject(
                        request.text,
                        backend="ollama",
                        override="LLM said ignore in LISTENING mode",
                    )

            # Sanity check: in IDLE mode
            if request.current_state == AppState.IDLE and request.trigger_phrase:
                text_lower = request.text.lower()
                trigger_found, _ = self._find_trigger_phrase(text_lower, request.trigger_phrase)

                # CRITICAL: Cannot change state without trigger phrase!
                if not trigger_found and action == Action.CHANGE_STATE:
                    if self._console:
                        self._console.print("[yellow]IDLE: LLM tried to change state without trigger phrase, ignoring[/]")
                    return LLMResponse.ignore("No trigger phrase for state change", backend="ollama")

                if trigger_found:
                    # Check for exit words - in IDLE mode, these should be ignored (can't exit what you're not in)
                    has_exit_word = any(kw in text_lower for kw in FALLBACK_EXIT_KEYWORDS)
                    has_enter_word = any(kw in text_lower for kw in FALLBACK_ENTER_KEYWORDS)

                    # If LLM says enter listening but text has exit words (not enter words) - override to ignore
                    if action == Action.CHANGE_STATE and new_state == AppState.LISTENING and has_exit_word and not has_enter_word:
                        if self._console:
                            self._console.print("[yellow]IDLE: LLM tried to enter LISTENING on exit word, ignoring[/]")
                        return LLMResponse.ignore("Exit word in IDLE mode", backend="ollama")

                    # If LLM says ignore but text has trigger + ascolta, override to enter
                    if action == Action.IGNORE and has_enter_word:
                        if self._console:
                            self._console.print(f"[yellow]LLM ignored trigger+enter word, overriding[/]")
                        return LLMResponse.enter_listening(backend="ollama")

                    # If LLM says ignore but text has trigger + target keywords, execute TARGET_ACTIVE
                    if action == Action.IGNORE:
                        for keyword in FALLBACK_TARGET_ACTIVE_KEYWORDS:
                            if keyword in text_lower:
                                if self._console:
                                    self._console.print(f"[yellow]LLM ignored trigger+'{keyword}', executing TARGET_ACTIVE[/]")
                                return LLMResponse.execute(Command.TARGET_ACTIVE, backend="ollama")

            return LLMResponse(
                action=action,
                new_state=new_state,
                text_to_inject=data.get("text_to_inject"),
                command=command,
                command_args=data.get("command_args"),
                user_feedback=data.get("user_feedback"),
                confidence=data.get("confidence", 1.0),
                backend="ollama",
                raw_llm_response=response_text[:500],  # Truncate for log size
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            if self._console:
                self._console.print(f"[yellow]Failed to parse LLM response: {e}[/]")
            # Fall back to keyword matching
            return self._process_with_keywords(request)

    def _process_with_keywords(self, request: LLMRequest) -> LLMResponse:
        """Fallback: process with keyword matching."""
        text_lower = request.text.lower().strip()

        # In LISTENING mode
        if request.current_state == AppState.LISTENING:
            # Only exit if it's a SHORT, explicit command (not embedded in a sentence)
            # This prevents "stop world" or "ho detto smetti" from triggering exit
            words = text_lower.split()
            if len(words) <= 3:  # Short phrase like "smetti", "ok stop", "Joshua smetti"
                for keyword in FALLBACK_EXIT_KEYWORDS:
                    if keyword in text_lower:
                        return LLMResponse.exit_listening()

            # Otherwise inject the text
            return LLMResponse.inject(request.text)

        # In IDLE mode - need trigger phrase
        if request.trigger_phrase:
            trigger_found, text_after = self._find_trigger_phrase(text_lower, request.trigger_phrase)

            if not trigger_found:
                return LLMResponse.ignore("No trigger phrase found", backend="keyword")

            # Check for enter keywords ANYWHERE in text (not just after trigger)
            # This handles both "Joshua ascolta" and "ascolta Joshua"
            for keyword in FALLBACK_ENTER_KEYWORDS:
                if keyword in text_lower:
                    return LLMResponse.enter_listening(backend="keyword")

            for keyword in FALLBACK_EXIT_KEYWORDS:
                if keyword in text_after:
                    return LLMResponse.exit_listening()

            for keyword in FALLBACK_PASTE_KEYWORDS:
                if keyword in text_after:
                    return LLMResponse.execute(Command.PASTE)

            for keyword in FALLBACK_UNDO_KEYWORDS:
                if keyword in text_after:
                    return LLMResponse.execute(Command.UNDO)

            for keyword in FALLBACK_REPEAT_KEYWORDS:
                if keyword in text_after:
                    return LLMResponse.execute(Command.REPEAT)

            for keyword in FALLBACK_TARGET_ACTIVE_KEYWORDS:
                if keyword in text_lower:  # Check full text, not just after trigger
                    return LLMResponse.execute(Command.TARGET_ACTIVE, backend="keyword")

            # Extract text to inject (text after trigger phrase)
            inject_text = self._extract_text_after_trigger(request)
            if inject_text:
                return LLMResponse.inject(inject_text)

            return LLMResponse.ignore("Trigger phrase only, no command")

        # No trigger phrase configured - inject everything
        return LLMResponse.inject(request.text)

    def _find_trigger_phrase(self, text_lower: str, trigger: str) -> tuple[bool, str]:
        """Find trigger phrase anywhere in text (fallback mode - exact match only).

        Note: This is used for keyword fallback only. The LLM handles phonetic
        variations intelligently. For fallback, we only match the exact trigger.

        Args:
            text_lower: Lowercase text to search.
            trigger: Trigger phrase to find.

        Returns:
            Tuple of (found, text_after_trigger).
        """
        trigger_lower = trigger.lower()
        if trigger_lower in text_lower:
            pos = text_lower.find(trigger_lower)
            text_after = text_lower[pos + len(trigger_lower):].strip()
            # Remove leading punctuation/separators
            text_after = text_after.lstrip(",:;.?! ")
            return True, text_after

        return False, ""

    def _extract_text_after_trigger(self, request: LLMRequest) -> str | None:
        """Extract and format text after trigger phrase (fallback mode - exact match only).

        Note: This is used for keyword fallback only. The LLM handles text
        extraction and formatting more intelligently.
        """
        if not request.trigger_phrase:
            return request.text

        text_lower = request.text.lower()
        trigger_lower = request.trigger_phrase.lower()

        if trigger_lower in text_lower:
            pos = text_lower.find(trigger_lower)
            # Get original case text after trigger
            text_after = request.text[pos + len(trigger_lower):].strip()
            # Remove leading punctuation
            text_after = text_after.lstrip(",:;.?! ")

            # Remove command keywords if present
            text_after_lower = text_after.lower()
            for kw in FALLBACK_ENTER_KEYWORDS + FALLBACK_EXIT_KEYWORDS:
                if text_after_lower.startswith(kw):
                    text_after = text_after[len(kw):].strip()
                    text_after = text_after.lstrip(",:;.?! ")
                    break

            return text_after if text_after else None

        return None

    def reset(self) -> None:
        """Reset processor state."""
        self._state = AppState.IDLE
        self._history.clear()
        self._last_injection = None
