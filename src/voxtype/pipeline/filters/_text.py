"""Shared text normalization utilities for pipeline filters."""

from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    """Normalize text for comparison.

    - Lowercase
    - Remove accents (NFD decomposition, strip combining chars)
    """
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


def tokenize(text: str) -> list[str]:
    """Split text into words, keeping only alphanumeric tokens."""
    return [w for w in re.split(r"[^a-zA-Z0-9]+", normalize(text)) if w]
