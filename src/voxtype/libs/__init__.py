"""Pure Python replacements for native-extension libraries.

Each module in this package replaces an external library whose native
extensions (Rust, C, etc.) cause Homebrew's ``install_name_tool`` to
fail with "header too small" during ``brew install``.

The modules expose the **same public interface** as the originals so
that switching back to the external dependency requires only changing
the import path.

Current replacements:

- ``jellyfish`` — phonetic matching (``metaphone``, ``levenshtein_distance``)
"""
