"""Pure Python replacement for the ``jellyfish`` library.

Replaces
--------
- **Package**: ``jellyfish`` (https://pypi.org/project/jellyfish/)
- **Version replaced**: ``>=1.0.0``
- **Reason**: jellyfish bundles a Rust native extension (``_rustyfish.so``)
  whose Mach-O headers are too small for Homebrew's ``install_name_tool``
  to rewrite during ``brew install``.  This causes a non-zero exit code
  and breaks chained install commands (``brew install && brew services start``).

Interface
---------
This module exposes the same function signatures as ``jellyfish``:

- ``metaphone(word: str) -> str``
- ``levenshtein_distance(s1: str, s2: str) -> int``

To switch back to the external library, change the import from::

    from dictare.libs.jellyfish import metaphone, levenshtein_distance

to::

    from jellyfish import metaphone, levenshtein_distance

No other code changes are needed.
"""

from __future__ import annotations

def metaphone(word: str) -> str:
    """Compute the Metaphone phonetic code for a word.

    Pure Python implementation of Lawrence Philips' Metaphone algorithm
    (1990).  Converts an English word into a rough phonetic representation
    so that words that sound alike produce the same code.

    Note: cyclomatic complexity is intentionally high (CC=62) — this is a
    faithful port of a phonetic algorithm consisting of sequential character
    pattern rules.  It is stable, well-tested, and not meant to be refactored
    into smaller functions.  The high CC eliminates a PyPI dependency whose
    Rust extension breaks Homebrew builds.

    Examples::

        >>> metaphone("koder")
        'KTR'
        >>> metaphone("coder")
        'KTR'
        >>> metaphone("python")
        'P0N'
    """
    if not word:
        return ""

    word = word.upper()
    word = "".join(c for c in word if c.isalpha())
    if not word:
        return ""

    # Drop first letter for silent-initial pairs
    if word[:2] in ("AE", "GN", "KN", "PN", "WR"):
        word = word[1:]
    if not word:
        return ""

    vowels = set("AEIOU")
    length = len(word)

    def _at(pos: int) -> str:
        return word[pos] if 0 <= pos < length else ""

    result: list[str] = []
    i = 0

    while i < length:
        c = word[i]

        # Skip duplicate adjacent letters (except C)
        if i > 0 and c == word[i - 1] and c != "C":
            i += 1
            continue

        if c in vowels:
            # Keep vowels only at the start of the word
            if i == 0:
                result.append(c)
            i += 1

        elif c == "B":
            # Silent B after M at end of word (DUMB → DM)
            if not (i == length - 1 and _at(i - 1) == "M"):
                result.append("B")
            i += 1

        elif c == "C":
            if _at(i + 1) == "I" and _at(i + 2) == "A":
                result.append("X")
                i += 3
            elif _at(i + 1) in ("E", "I", "Y"):
                result.append("S")
                i += 2
            elif _at(i + 1) == "H":
                # SCH → SK, otherwise CH → X
                result.append("K" if i > 0 and _at(i - 1) == "S" else "X")
                i += 2
            else:
                result.append("K")
                i += 1

        elif c == "D":
            if _at(i + 1) == "G" and _at(i + 2) in ("E", "I", "Y"):
                result.append("J")
                i += 3
            else:
                result.append("T")
                i += 1

        elif c == "F":
            result.append("F")
            i += 1

        elif c == "G":
            if _at(i + 1) == "H":
                if i + 2 < length and _at(i + 2) not in vowels:
                    i += 2  # GH before consonant → silent
                else:
                    result.append("K")
                    i += 2
            elif _at(i + 1) == "N":
                i += 1  # G before N → silent
            elif _at(i + 1) in ("E", "I", "Y"):
                result.append("J")
                i += 1
            else:
                result.append("K")
                i += 1

        elif c == "H":
            # Keep H only if before a vowel and not after a vowel
            if _at(i + 1) in vowels and _at(i - 1) not in vowels:
                result.append("H")
            i += 1

        elif c == "J":
            result.append("J")
            i += 1

        elif c == "K":
            # Silent K after C (already encoded by C → K)
            if i == 0 or _at(i - 1) != "C":
                result.append("K")
            i += 1

        elif c == "L":
            result.append("L")
            i += 1

        elif c == "M":
            result.append("M")
            i += 1

        elif c == "N":
            result.append("N")
            i += 1

        elif c == "P":
            if _at(i + 1) == "H":
                result.append("F")
                i += 2
            else:
                result.append("P")
                i += 1

        elif c == "Q":
            result.append("K")
            i += 1

        elif c == "R":
            result.append("R")
            i += 1

        elif c == "S":
            if _at(i + 1) == "H":
                result.append("X")
                i += 2
            elif _at(i + 1) == "I" and _at(i + 2) in ("A", "O"):
                result.append("X")
                i += 3
            else:
                result.append("S")
                i += 1

        elif c == "T":
            if _at(i + 1) == "H":
                result.append("0")  # θ
                i += 2
            elif _at(i + 1) == "I" and _at(i + 2) in ("A", "O"):
                result.append("X")
                i += 3
            else:
                result.append("T")
                i += 1

        elif c == "V":
            result.append("F")
            i += 1

        elif c == "W":
            if _at(i + 1) in vowels:
                result.append("W")
            i += 1

        elif c == "X":
            result.append("KS")
            i += 1

        elif c == "Y":
            if _at(i + 1) in vowels:
                result.append("Y")
            i += 1

        elif c == "Z":
            result.append("S")
            i += 1

        else:
            i += 1

    return "".join(result)

def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein (edit) distance between two strings.

    Returns the minimum number of single-character edits (insertions,
    deletions, or substitutions) needed to transform ``s1`` into ``s2``.

    Examples::

        >>> levenshtein_distance("hello", "hello")
        0
        >>> levenshtein_distance("koder", "coder")
        1
        >>> levenshtein_distance("abc", "xyz")
        3
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if not s2:
        return len(s1)

    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(
                prev[j + 1] + 1,       # deletion
                curr[j] + 1,            # insertion
                prev[j] + (c1 != c2),   # substitution
            ))
        prev = curr
    return prev[-1]
