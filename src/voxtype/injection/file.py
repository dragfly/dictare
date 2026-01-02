"""File-based text injection - writes to a file instead of typing.

Protocol for inputmux:
- \\n = visual newline → inputmux sends Alt+Enter
- <<SUBMIT>> = submit → inputmux sends Enter
"""

from __future__ import annotations

from pathlib import Path

from voxtype.injection.base import TextInjector

# Submit token for the file protocol
SUBMIT_TOKEN = "<<SUBMIT>>"


class FileInjector(TextInjector):
    """Writes text to a file (append mode).

    Uses a protocol that inputmux interprets:
    - \\n = visual newline (inputmux sends Alt+Enter)
    - <<SUBMIT>> = submit (inputmux sends Enter)
    """

    def __init__(self, filepath: str | Path) -> None:
        self.filepath = Path(filepath)

    def is_available(self) -> bool:
        """Always available - files always work."""
        return True

    def type_text(self, text: str, delay_ms: int = 0, auto_enter: bool = True) -> bool:
        """Append text to file.

        Args:
            text: Text to write.
            delay_ms: Ignored for file output.
            auto_enter: If True, add newline + submit token after text.
                        If False, just write text (send_newline adds visual newline).

        Returns:
            True if successful.
        """
        try:
            # Strip trailing newline - we handle it based on auto_enter
            if text.endswith("\n"):
                text = text.rstrip("\n")

            with open(self.filepath, "ab") as f:
                f.write(text.encode())
                # Add newline + submit token if auto_enter
                if auto_enter:
                    f.write(f"\n{SUBMIT_TOKEN}\n".encode())
                f.flush()
            return True
        except OSError:
            return False

    def get_name(self) -> str:
        """Get the name of this injector."""
        return f"file:{self.filepath}"

    def send_newline(self) -> bool:
        """Write a newline to the file.

        Inputmux interprets this as Alt+Enter (visual newline).
        """
        try:
            with open(self.filepath, "ab") as f:
                f.write(b"\n")
                f.flush()
            return True
        except OSError:
            return False

    def send_submit(self) -> bool:
        """Write a submit token to the file.

        Inputmux interprets this as Enter (submit).
        """
        try:
            with open(self.filepath, "ab") as f:
                f.write(f"{SUBMIT_TOKEN}\n".encode())
                f.flush()
            return True
        except OSError:
            return False
