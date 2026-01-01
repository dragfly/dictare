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

    def type_text(self, text: str, delay_ms: int = 0) -> bool:
        """Append text to file.

        Args:
            text: Text to write.
            delay_ms: Ignored for file output.

        Returns:
            True if successful.
        """
        try:
            with open(self.filepath, "a") as f:
                f.write(text + "\n")
                f.flush()
            return True
        except OSError:
            return False

    def get_name(self) -> str:
        """Get the name of this injector."""
        return f"file:{self.filepath}"
