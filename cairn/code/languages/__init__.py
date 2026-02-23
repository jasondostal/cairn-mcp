"""Language registry for tree-sitter parsers.

Adding a new language:
  1. Create cairn/code/languages/<lang>.py with a get_language() function
     that returns a tree_sitter.Language and an extract_symbols() function.
  2. Register the extension mapping below.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter as ts

logger = logging.getLogger(__name__)

# Extension -> module name mapping
_EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript_tsx",
}

# Cached language modules
_LOADED: dict[str, object] = {}


def language_for_extension(ext: str) -> str | None:
    """Return the language name for a file extension, or None if unsupported."""
    return _EXTENSION_MAP.get(ext)


def supported_extensions() -> set[str]:
    """Return all supported file extensions."""
    return set(_EXTENSION_MAP.keys())


def get_language_module(lang: str):
    """Lazily load and return a language module.

    Each module must expose:
      - get_language() -> tree_sitter.Language
      - extract_symbols(tree, source, file_path) -> list[CodeSymbol]
    """
    if lang in _LOADED:
        return _LOADED[lang]

    if lang == "python":
        from cairn.code.languages import python as mod
    elif lang in ("typescript", "typescript_tsx"):
        from cairn.code.languages import typescript as mod
    else:
        raise ValueError(f"Unsupported language: {lang}")

    _LOADED[lang] = mod
    return mod
