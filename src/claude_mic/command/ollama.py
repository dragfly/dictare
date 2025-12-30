"""Ollama-based intent classification."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Optional

from claude_mic.command.base import (
    CommandIntent,
    CommandResult,
    IntentClassifier,
)

class OllamaClassifier(IntentClassifier):
    """Intent classification using local Ollama LLM.

    Uses a small, fast model to classify voice commands and optionally
    format/clean the transcribed text.
    """

    SYSTEM_PROMPT = """Sei l'assistente vocale Joshua per claude-mic.
Il tuo compito è classificare comandi vocali in italiano o inglese.

Intenti disponibili:
- ascolta: L'utente vuole entrare in modalità ascolto continuo
- smetti: L'utente vuole uscire dalla modalità ascolto
- incolla: L'utente vuole incollare dalla clipboard
- annulla: L'utente vuole annullare l'ultima azione (undo)
- ripeti: L'utente vuole ripetere l'ultima trascrizione
- target_window: L'utente vuole cambiare la finestra target (es. "invia al terminal")
- text: Testo normale da digitare (non è un comando)

Rispondi SOLO con un oggetto JSON valido:
{
  "intent": "ascolta|smetti|incolla|annulla|ripeti|target_window|text",
  "confidence": 0.0-1.0,
  "formatted_text": "testo formattato con punteggiatura corretta",
  "target_query": "nome finestra se intent=target_window, altrimenti null"
}"""

    def __init__(
        self,
        model: str = "llama3.2:1b",
        timeout: float = 5.0,
        fallback: Optional[IntentClassifier] = None,
        format_text: bool = True,
    ) -> None:
        """Initialize Ollama classifier.

        Args:
            model: Ollama model to use (small, fast model recommended).
            timeout: Request timeout in seconds.
            fallback: Fallback classifier if Ollama fails.
            format_text: Whether to use LLM to format/clean text.
        """
        self.model = model
        self.timeout = timeout
        self.fallback = fallback
        self.format_text = format_text
        self._ollama_path: str | None = None
        self._available: bool | None = None

    def classify(self, text: str) -> CommandResult:
        """Classify using Ollama."""
        if not self._ollama_path:
            self._ollama_path = shutil.which("ollama")

        if not self._ollama_path:
            return self._use_fallback(text, "Ollama not found")

        prompt = f'Classifica questo comando vocale: "{text}"'

        try:
            # Use ollama API via subprocess for simplicity
            result = subprocess.run(
                [
                    self._ollama_path,
                    "run",
                    self.model,
                    f"{self.SYSTEM_PROMPT}\n\nUser: {prompt}",
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode != 0:
                return self._use_fallback(text, f"Ollama error: {result.stderr}")

            # Parse JSON response
            response_text = result.stdout.strip()

            # Extract JSON from response (model might include extra text)
            json_match = self._extract_json(response_text)
            if not json_match:
                return self._use_fallback(text, f"No JSON in response: {response_text[:100]}")

            response = json.loads(json_match)
            intent_str = response.get("intent", "text").lower()
            confidence = float(response.get("confidence", 0.5))
            formatted_text = response.get("formatted_text", text)
            target_query = response.get("target_query")

            # Map string to enum
            intent_map = {
                "ascolta": CommandIntent.ASCOLTA,
                "smetti": CommandIntent.SMETTI,
                "incolla": CommandIntent.INCOLLA,
                "annulla": CommandIntent.ANNULLA,
                "ripeti": CommandIntent.RIPETI,
                "target_window": CommandIntent.TARGET_WINDOW,
                "text": CommandIntent.TEXT,
            }

            intent = intent_map.get(intent_str, CommandIntent.TEXT)

            return CommandResult(
                intent=intent,
                confidence=confidence,
                original_text=text,
                formatted_text=formatted_text if self.format_text else text,
                target_query=target_query if intent == CommandIntent.TARGET_WINDOW else None,
            )

        except subprocess.TimeoutExpired:
            return self._use_fallback(text, "Ollama timeout")
        except json.JSONDecodeError as e:
            return self._use_fallback(text, f"JSON parse error: {e}")
        except Exception as e:
            return self._use_fallback(text, str(e))

    def _extract_json(self, text: str) -> str | None:
        """Extract JSON object from text."""
        # Find JSON object in response
        start = text.find("{")
        if start == -1:
            return None

        # Find matching closing brace
        depth = 0
        for i, char in enumerate(text[start:], start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None

    def _use_fallback(self, text: str, reason: str) -> CommandResult:
        """Use fallback classifier or return TEXT intent."""
        if self.fallback:
            return self.fallback.classify(text)

        # No fallback - treat as regular text
        return CommandResult(
            intent=CommandIntent.TEXT,
            confidence=0.5,
            original_text=text,
            formatted_text=text,
        )

    def is_available(self) -> bool:
        """Check if Ollama is available and model exists."""
        if self._available is not None:
            return self._available

        self._ollama_path = shutil.which("ollama")
        if not self._ollama_path:
            self._available = False
            return False

        # Check if model is available
        try:
            result = subprocess.run(
                [self._ollama_path, "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            model_base = self.model.split(":")[0]
            self._available = model_base in result.stdout
            return self._available
        except Exception:
            self._available = False
            return False

    def get_name(self) -> str:
        """Get classifier name."""
        return f"ollama ({self.model})"
