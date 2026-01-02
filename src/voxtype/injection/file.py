"""File-based text injection - writes to a file instead of typing."""

from __future__ import annotations

from pathlib import Path

from voxtype.injection.base import TextInjector


class FileInjector(TextInjector):
    """Writes text to a file (append mode)."""

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
            auto_enter: If True and text ends with newline, keep it (submit signal).
                        If False, strip trailing newline (text accumulates).

        Returns:
            True if successful.
        """
        try:
            # Handle newline at end based on auto_enter mode
            # When auto_enter=False, strip trailing newline to prevent submit
            if not auto_enter and text.endswith("\n"):
                text = text.rstrip("\n")

            with open(self.filepath, "ab") as f:
                f.write(text.encode())
                f.flush()
            return True
        except OSError:
            return False

    def get_name(self) -> str:
        """Get the name of this injector."""
        return f"file:{self.filepath}"

    def send_newline(self) -> bool:
        """Write a space separator to the file.

        For file mode, newline means 'submit' to the reader (inputmux).
        So for visual separation between phrases, we use a space instead.
        """
        try:
            with open(self.filepath, "ab") as f:
                f.write(b" ")
                f.flush()
            return True
        except OSError:
            return False

    def send_submit(self) -> bool:
        """Write a submit marker to the file.

        For file mode, we write a special marker that readers can detect.
        """
        try:
            with open(self.filepath, "ab") as f:
                f.write(b"\n---SUBMIT---\n")
                f.flush()
            return True
        except OSError:
            return False
