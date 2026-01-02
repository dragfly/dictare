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
            auto_enter: Ignored for file output (newlines always written).

        Returns:
            True if successful.
        """
        try:
            with open(self.filepath, "ab") as f:
                # Write text as-is (already has \n from auto_enter)
                f.write(text.encode())
                f.flush()
            return True
        except OSError:
            return False

    def get_name(self) -> str:
        """Get the name of this injector."""
        return f"file:{self.filepath}"

    def send_newline(self) -> bool:
        """Write a newline to the file."""
        try:
            with open(self.filepath, "ab") as f:
                f.write(b"\n")
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
