"""Language registry for tree-sitter parsers.

Adding a new language:
  1. Create cairn/code/languages/<lang>.py with a get_language() function
     that returns a tree_sitter.Language and an extract_symbols() function.
  2. Register the extension mapping below.
"""

from __future__ import annotations

import logging

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
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".lua": "lua",
    ".groovy": "groovy",
    ".gradle": "groovy",
    ".m": "objc",
    ".mm": "objc",
    ".zig": "zig",
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".mat": "matlab",
}

# Filename -> module name mapping (for files without useful extensions)
_FILENAME_MAP: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "GNUmakefile": "makefile",
    "makefile": "makefile",
    "Jenkinsfile": "groovy",
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


import importlib
import types

# Language name -> module path within cairn.code.languages
_LANG_MODULES: dict[str, str] = {
    "python": "python",
    "typescript": "typescript",
    "typescript_tsx": "typescript",
    "golang": "go",
    "rust": "rust",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "php": "php",
    "ruby": "ruby",
    "json": "json",
    "yaml": "yaml",
    "bash": "bash",
    "sql": "sql",
    "markdown": "markdown",
    "swift": "swift",
    "scala": "scala",
    "kotlin": "kotlin",
    "csharp": "csharp",
    "hcl": "hcl",
    "toml": "toml",
    "dockerfile": "dockerfile",
    "html": "html",
    "css": "css",
    "lua": "lua",
    "groovy": "groovy",
    "makefile": "makefile",
    "objc": "objc",
    "zig": "zig",
    "ocaml": "ocaml",
    "matlab": "matlab",
}


def get_language_module(lang: str) -> types.ModuleType:
    """Lazily load and return a language module.

    Each module must expose:
      - get_language() -> tree_sitter.Language
      - extract_symbols(tree, source, file_path) -> list[CodeSymbol]
    """
    if lang in _LOADED:
        return _LOADED[lang]  # type: ignore[return-value]

    module_name = _LANG_MODULES.get(lang)
    if module_name is None:
        raise ValueError(f"Unsupported language: {lang}")

    mod = importlib.import_module(f"cairn.code.languages.{module_name}")
    _LOADED[lang] = mod
    return mod
