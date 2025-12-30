"""LLM-first processing module.

All transcribed text goes through the LLM, which decides:
- Is it a command? (ascolta, smetti, incolla, etc.)
- State change? (enter/exit LISTENING mode)
- Text to inject?
- Should be ignored? (no trigger phrase, noise, etc.)
"""

from claude_mic.llm.models import Action, AppState, Command, LLMRequest, LLMResponse
from claude_mic.llm.processor import LLMProcessor

__all__ = [
    "Action",
    "AppState",
    "Command",
    "LLMProcessor",
    "LLMRequest",
    "LLMResponse",
]
