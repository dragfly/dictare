"""File-based text injection - writes JSONL to a file.

JSONL Protocol for inputmux:
- {"text": "hello"}                 → type "hello"
- {"text": "hello", "submit": true} → type "hello" + Enter (submit)
- {"text": "\\n"}                   → Alt+Enter (visual newline)
- {"submit": true}                  → just Enter

Each message includes:
- ts: ISO timestamp when message was written
- v: voxtype version that wrote the message
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from voxtype import __version__
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

    def _write_message(self, msg: dict[str, Any]) -> bool:
        """Write a JSONL message to the file with timestamp and version."""
        try:
            # Add metadata for debugging
            msg["ts"] = datetime.now(timezone.utc).isoformat()
            msg["v"] = __version__
            with open(self.filepath, "a") as f:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                f.flush()
            return True
        except OSError:
            return False

    def type_text(self, text: str, delay_ms: int = 0, auto_enter: bool = True) -> bool:
        """Write text as JSONL message.

        The consumer handles message termination:
        - submit=true: text + Enter
        - text ends with \\n: visual newline (Alt+Enter)

        Args:
            text: Text to write (without trailing newline).
            delay_ms: Ignored for file output.
            auto_enter: If True, add submit flag. If False, add visual newline.

        Returns:
            True if successful.
        """
        ts = datetime.now(timezone.utc).isoformat()
        msg: dict[str, Any] = {"text": text, "ts": ts, "v": __version__}
        if auto_enter:
            msg["submit"] = True

        try:
            output = json.dumps(msg, ensure_ascii=False) + "\n"
            # When auto_enter=false, include visual newline message atomically
            if not auto_enter:
                newline_msg = {"text": "\n", "ts": ts, "v": __version__}
                output += json.dumps(newline_msg, ensure_ascii=False) + "\n"

            with open(self.filepath, "a") as f:
                f.write(output)  # Single write = single FS event
                f.flush()
            return True
        except OSError:
            return False

    def get_name(self) -> str:
        """Get the name of this injector."""
        return f"file:{self.filepath}"

    def send_newline(self) -> bool:
        """Write a standalone visual newline."""
        return self._write_message({"text": "\n"})

    def send_submit(self) -> bool:
        """Write a submit message (Enter key)."""
        return self._write_message({"submit": True})
