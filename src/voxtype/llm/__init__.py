"""LLM-first processing module.

All transcribed text goes through the LLM, which decides:
- Is it a command? (ascolta, smetti, incolla, etc.)
- State change? (enter/exit LISTENING mode)
- Text to inject?
- Should be ignored? (no trigger phrase, noise, etc.)
"""

from voxtype.llm.models import Action, AppState, Command, LLMRequest, LLMResponse
from voxtype.llm.processor import LLMProcessor

__all__ = [
    "Action",
    "AppState",
    "Command",
    "LLMProcessor",
    "LLMRequest",
    "LLMResponse",
]
