"""Extract imports from Python files using stdlib ast.

No external dependencies. Parses a Python file and returns every imported
module path — both ``import X`` and ``from X import Y`` forms.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ImportInfo:
    """A single import found in a source file."""
    module: str                # Fully-qualified module path (e.g. "cairn.core.services")
    names: tuple[str, ...]     # Names imported from that module (empty for plain ``import X``)
    lineno: int                # Line number in source
    is_from: bool              # True for ``from X import Y``, False for ``import X``


@dataclass
class FileImports:
    """All imports extracted from one Python file."""
    path: Path
    imports: list[ImportInfo] = field(default_factory=list)
    error: str | None = None   # Set if parsing failed

    @property
    def module_paths(self) -> list[str]:
        """Unique imported module paths, sorted."""
        return sorted({imp.module for imp in self.imports})


def extract_imports(source: str, path: Path | None = None) -> FileImports:
    """Parse Python source and extract all imports.

    Args:
        source: Python source code as a string.
        path: Optional file path (for error reporting).

    Returns:
        FileImports with all discovered imports, or an error message if
        the file couldn't be parsed.
    """
    result = FileImports(path=path or Path("<string>"))

    try:
        tree = ast.parse(source, filename=str(result.path))
    except SyntaxError as e:
        result.error = f"SyntaxError: {e}"
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.imports.append(ImportInfo(
                    module=alias.name,
                    names=(),
                    lineno=node.lineno,
                    is_from=False,
                ))
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue  # relative import with no module (``from . import X``)
            result.imports.append(ImportInfo(
                module=node.module,
                names=tuple(a.name for a in node.names),
                lineno=node.lineno,
                is_from=True,
            ))

    return result


def extract_imports_from_file(filepath: Path) -> FileImports:
    """Read a Python file and extract its imports."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return FileImports(path=filepath, error=str(e))
    return extract_imports(source, filepath)


def extract_imports_from_directory(root: Path, exclude: set[str] | None = None) -> list[FileImports]:
    """Recursively extract imports from all .py files under ``root``.

    Args:
        root: Directory to scan.
        exclude: Directory names to skip (e.g. {"__pycache__", ".venv"}).

    Returns:
        List of FileImports, one per .py file found.
    """
    exclude = exclude or {"__pycache__", ".venv", "node_modules", ".git"}
    results: list[FileImports] = []

    for py_file in sorted(root.rglob("*.py")):
        # Skip excluded directories
        if any(part in exclude for part in py_file.parts):
            continue
        results.append(extract_imports_from_file(py_file))

    return results
