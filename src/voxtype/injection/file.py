"""File-based text injection - writes JSONL to a file.

JSONL Protocol for inputmux:
- {"text": "hello"}                 → type "hello"
- {"text": "hello\\n"}              → type "hello" + Alt+Enter (visual newline)
- {"text": "hello", "submit": true} → type "hello" + Enter (submit)
- {"submit": true}                  → just Enter
"""

from __future__ import annotations

import json
from pathlib import Path

from voxtype.injection.base import TextInjector

class FileInjector(TextInjector):
    """Writes JSONL messages to a file (append mode).

    Each line is a JSON object that inputmux interprets:
    - text: string to type (trailing \\n = Alt+Enter)
    - submit: if true, send Enter after text
    """

    def __init__(self, filepath: str | Path) -> None:
        self.filepath = Path(filepath)

    def is_available(self) -> bool:
        """Always available - files always work."""
        return True

    def _write_message(self, msg: dict) -> bool:
        """Write a JSONL message to the file."""
        try:
            with open(self.filepath, "a") as f:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                f.flush()
            return True
        except OSError:
            return False

    def type_text(self, text: str, delay_ms: int = 0, auto_enter: bool = True) -> bool:
        """Write text as JSONL message.

        Args:
            text: Text to write (trailing \\n preserved for visual newline).
            delay_ms: Ignored for file output.
            auto_enter: If True, add submit flag for Enter.

        Returns:
            True if successful.
        """
        msg = {"text": text}
        if auto_enter:
            msg["submit"] = True

        return self._write_message(msg)

    def get_name(self) -> str:
        """Get the name of this injector."""
        return f"file:{self.filepath}"

    def send_newline(self) -> bool:
        """Write a visual newline (text with trailing \\n)."""
        return self._write_message({"text": "\n"})

    def send_submit(self) -> bool:
        """Write a submit message (Enter key)."""
        return self._write_message({"submit": True})
