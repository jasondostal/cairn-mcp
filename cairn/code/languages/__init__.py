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
    ".go": "golang",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".php": "php",
    ".rb": "ruby",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".md": "markdown",
    ".markdown": "markdown",
    ".swift": "swift",
    ".scala": "scala",
    ".sc": "scala",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".tf": "hcl",
    ".hcl": "hcl",
    ".toml": "toml",
    ".dockerfile": "dockerfile",
}

# Filename -> module name mapping (for files without useful extensions)
_FILENAME_MAP: dict[str, str] = {
    "Dockerfile": "dockerfile",
}

# Cached language modules
_LOADED: dict[str, object] = {}


def language_for_extension(ext: str) -> str | None:
    """Return the language name for a file extension, or None if unsupported."""
    return _EXTENSION_MAP.get(ext)


def language_for_filename(name: str) -> str | None:
    """Return the language name for a filename, or None if unrecognised."""
    return _FILENAME_MAP.get(name)


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
    elif lang == "golang":
        from cairn.code.languages import go as mod
    elif lang == "rust":
        from cairn.code.languages import rust as mod
    elif lang == "java":
        from cairn.code.languages import java as mod
    elif lang == "c":
        from cairn.code.languages import c as mod
    elif lang == "cpp":
        from cairn.code.languages import cpp as mod
    elif lang == "php":
        from cairn.code.languages import php as mod
    elif lang == "ruby":
        from cairn.code.languages import ruby as mod
    elif lang == "json":
        from cairn.code.languages import json as mod
    elif lang == "yaml":
        from cairn.code.languages import yaml as mod
    elif lang == "bash":
        from cairn.code.languages import bash as mod
    elif lang == "sql":
        from cairn.code.languages import sql as mod
    elif lang == "markdown":
        from cairn.code.languages import markdown as mod
    elif lang == "swift":
        from cairn.code.languages import swift as mod
    elif lang == "scala":
        from cairn.code.languages import scala as mod
    elif lang == "kotlin":
        from cairn.code.languages import kotlin as mod
    elif lang == "csharp":
        from cairn.code.languages import csharp as mod
    elif lang == "hcl":
        from cairn.code.languages import hcl as mod
    elif lang == "toml":
        from cairn.code.languages import toml as mod
    elif lang == "dockerfile":
        from cairn.code.languages import dockerfile as mod
    else:
        raise ValueError(f"Unsupported language: {lang}")

    _LOADED[lang] = mod
    return mod
