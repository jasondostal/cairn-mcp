"""Language-agnostic code parser using tree-sitter.

Parses source files into structured CodeSymbol objects. Delegates to
language-specific modules in cairn.code.languages for AST extraction.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter as ts

from cairn.code.languages import (
    get_language_module,
    language_for_extension,
    language_for_filename,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodeSymbol:
    """A symbol extracted from source code."""
    name: str                       # Short name (e.g. "search", "MyClass")
    qualified_name: str             # Full name (e.g. "MyClass.search")
    kind: str                       # "function", "method", "class", "import", "constant"
    file_path: str                  # File this symbol was found in
    start_line: int                 # 1-based
    end_line: int                   # 1-based
    signature: str = ""             # e.g. "def search(self, query: str) -> list"
    docstring: str | None = None
    parent_name: str | None = None  # Containing class/function name


@dataclass
class ParseResult:
    """Result of parsing one source file."""
    file_path: str
    language: str
    content_hash: str               # SHA-256 of file content
    symbols: list[CodeSymbol] = field(default_factory=list)
    imports: list[CodeSymbol] = field(default_factory=list)  # Subset: kind == "import"
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def all_symbols(self) -> list[CodeSymbol]:
        """All symbols including imports."""
        return self.symbols + self.imports


class CodeParser:
    """Parse source files using tree-sitter.

    Usage:
        parser = CodeParser()
        result = parser.parse_file(Path("cairn/core/search.py"))
        for sym in result.symbols:
            print(sym.qualified_name, sym.kind, sym.start_line)
    """

    def __init__(self):
        self._parsers: dict[str, ts.Parser] = {}

    def _get_parser(self, language: str) -> ts.Parser:
        """Get or create a tree-sitter parser for a language."""
        if language not in self._parsers:
            mod = get_language_module(language)
            # TypeScript module needs a dialect param (typescript vs tsx)
            if language == "typescript_tsx":
                lang = mod.get_language("tsx")
            elif language == "typescript":
                lang = mod.get_language("typescript")
            else:
                lang = mod.get_language()
            self._parsers[language] = ts.Parser(lang)
        return self._parsers[language]

    def parse_source(self, source: str, language: str, file_path: str = "<string>") -> ParseResult:
        """Parse source code string and extract symbols."""
        source_bytes = source.encode("utf-8")
        content_hash = hashlib.sha256(source_bytes).hexdigest()

        try:
            parser = self._get_parser(language)
            tree = parser.parse(source_bytes)
        except Exception as e:
            return ParseResult(
                file_path=file_path,
                language=language,
                content_hash=content_hash,
                error=f"Parse error: {e}",
            )

        try:
            mod = get_language_module(language)
            all_syms = mod.extract_symbols(tree, source_bytes, file_path)
        except Exception as e:
            return ParseResult(
                file_path=file_path,
                language=language,
                content_hash=content_hash,
                error=f"Symbol extraction error: {e}",
            )

        # Split imports from other symbols
        imports = [s for s in all_syms if s.kind == "import"]
        symbols = [s for s in all_syms if s.kind != "import"]

        return ParseResult(
            file_path=file_path,
            language=language,
            content_hash=content_hash,
            symbols=symbols,
            imports=imports,
        )

    def parse_file(self, filepath: Path) -> ParseResult | None:
        """Parse a file from disk. Returns None if the language is unsupported."""
        ext = filepath.suffix
        language = language_for_extension(ext)
        if language is None:
            language = language_for_filename(filepath.name)
        if language is None:
            return None

        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return ParseResult(
                file_path=str(filepath),
                language=language,
                content_hash="",
                error=str(e),
            )

        return self.parse_source(source, language, str(filepath))

    def parse_directory(
        self,
        root: Path,
        exclude: set[str] | None = None,
    ) -> list[ParseResult]:
        """Parse all supported files under a directory.

        Respects all .gitignore files in the tree (root and nested). The .git
        directory is always excluded regardless of .gitignore contents.

        Args:
            root: Directory to scan.
            exclude: Additional directory names to skip (on top of .gitignore).

        Returns:
            List of ParseResult, one per supported file found.
        """
        import pathspec

        from cairn.code.languages import supported_extensions

        exclude = exclude or set()
        # .git is always excluded — it's not source code
        exclude.add(".git")

        # Collect all .gitignore files: (directory, PathSpec) pairs
        gitignore_specs: list[tuple[Path, pathspec.PathSpec]] = []
        for gi_path in root.rglob(".gitignore"):
            if any(part in exclude for part in gi_path.parts):
                continue
            with open(gi_path) as f:
                spec = pathspec.PathSpec.from_lines("gitwildmatch", f)
            gitignore_specs.append((gi_path.parent, spec))

        def _is_ignored(filepath: Path) -> bool:
            for gi_dir, spec in gitignore_specs:
                try:
                    rel = filepath.relative_to(gi_dir)
                except ValueError:
                    continue
                if spec.match_file(str(rel)):
                    return True
            return False

        from cairn.code.languages import language_for_filename as _lang_for_name

        exts = supported_extensions()
        results: list[ParseResult] = []

        for filepath in sorted(root.rglob("*")):
            if not filepath.is_file():
                continue
            if filepath.suffix not in exts and _lang_for_name(filepath.name) is None:
                continue
            if any(part in exclude for part in filepath.parts):
                continue
            if _is_ignored(filepath):
                continue

            result = self.parse_file(filepath)
            if result is not None:
                results.append(result)

        return results
