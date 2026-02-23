"""Shared utilities for the code intelligence module."""

from __future__ import annotations

from pathlib import Path


def path_to_module(file_path: str) -> str | None:
    """Convert a file path to a dotted module path.

    e.g. "cairn/core/search.py" -> "cairn.core.search"
         "cairn/core/__init__.py" -> "cairn.core"
    """
    path = Path(file_path)
    if path.suffix != ".py":
        return None
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


def path_to_module_ts(file_path: str) -> str | None:
    """Convert a TS/TSX file path to a dotted module identifier.

    e.g. "src/components/Button.tsx" -> "src.components.Button"
         "src/utils/index.ts" -> "src.utils"
    """
    path = Path(file_path)
    if path.suffix not in (".ts", ".tsx"):
        return None
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "index":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


def resolve_ts_import(import_path: str, importer_dir: str, known_files: set[str]) -> str | None:
    """Resolve a TypeScript import specifier to a file path.

    Handles:
    - Relative imports: ./foo, ../bar
    - Index files: ./components -> ./components/index.ts
    - Extension-optional: ./utils -> ./utils.ts or ./utils.tsx

    Args:
        import_path: The import specifier (e.g. "./utils", "../components/Button").
        importer_dir: Directory of the importing file.
        known_files: Set of all known file paths in the project.

    Returns:
        Resolved file path or None if not found.
    """
    if not import_path.startswith("."):
        return None  # Bare specifier (e.g. "react") — external dependency

    import posixpath
    base_str = posixpath.normpath(posixpath.join(importer_dir, import_path))

    # Try exact match (already has extension)
    if base_str in known_files:
        return base_str

    # Try adding extensions
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        candidate = base_str + ext
        if candidate in known_files:
            return candidate

    # Try as directory with index file
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        candidate = posixpath.join(base_str, "index") + ext
        if candidate in known_files:
            return candidate

    return None
