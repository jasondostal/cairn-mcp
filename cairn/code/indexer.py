"""Code indexer: parse source files and store results in the code graph.

Connects the CodeParser (tree-sitter) to the GraphProvider (Neo4j).
Content-hash dedup ensures unchanged files are never re-processed.

Performance: uses batch_upsert_code_graph to collapse all Neo4j writes into
a single transaction (typically 6 Cypher statements instead of hundreds).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from cairn.code.parser import CodeParser, ParseResult
from cairn.code.utils import path_to_module, path_to_module_ts, resolve_ts_import
from cairn.graph.interface import GraphProvider

logger = logging.getLogger(__name__)


@dataclass
class IndexResult:
    """Summary of an indexing operation."""
    project: str
    project_id: int
    files_scanned: int = 0
    files_indexed: int = 0       # Actually parsed and stored (new or changed)
    files_skipped: int = 0       # Unchanged (hash match)
    files_deleted: int = 0       # Removed from graph (file no longer exists)
    symbols_created: int = 0
    imports_created: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        parts = [
            f"Indexed {self.files_indexed} files",
            f"({self.files_skipped} unchanged, {self.files_deleted} deleted)",
            f"— {self.symbols_created} symbols, {self.imports_created} imports",
        ]
        if self.errors:
            parts.append(f", {len(self.errors)} errors")
        return " ".join(parts)


class CodeIndexer:
    """Parse source files and store the code graph in Neo4j.

    Usage:
        indexer = CodeIndexer(parser, graph_provider)
        result = indexer.index_directory(project="cairn", project_id=1,
                                          root=Path("cairn"))
    """

    def __init__(self, parser: CodeParser, graph: GraphProvider):
        self.parser = parser
        self.graph = graph

    def index_file(
        self,
        filepath: Path,
        project: str,
        project_id: int,
        force: bool = False,
    ) -> IndexResult:
        """Index a single file. Skips if content hash is unchanged."""
        result = IndexResult(project=project, project_id=project_id)
        result.files_scanned = 1

        parsed = self.parser.parse_file(filepath)
        if parsed is None:
            return result  # Unsupported language

        if not parsed.ok:
            result.errors.append(f"{filepath}: {parsed.error}")
            return result

        # Check if already indexed with same hash
        if not force:
            existing = self.graph.get_code_file(str(filepath), project_id)
            if existing and existing.get("content_hash") == parsed.content_hash:
                result.files_skipped = 1
                return result

        # Single-file batch upsert
        file_dict = _parsed_to_dict(parsed)
        self.graph.batch_upsert_code_graph(
            project_id=project_id,
            files=[file_dict],
            import_edges=[],
            stale_file_uuids=[],
        )
        result.files_indexed = 1
        result.symbols_created = len(parsed.symbols)
        result.imports_created = len(parsed.imports)

        return result

    def index_directory(
        self,
        root: Path,
        project: str,
        project_id: int,
        force: bool = False,
        exclude: set[str] | None = None,
    ) -> IndexResult:
        """Index all supported files under a directory.

        Respects .gitignore if present. Phase 1: Parse all files (CPU-only,
        no I/O to Neo4j). Phase 2: Diff against existing graph to find
        changed files. Phase 3: Batch-upsert in chunked Neo4j transactions.
        """
        result = IndexResult(project=project, project_id=project_id)

        # Phase 1: Parse all files (CPU-bound, no graph I/O)
        parsed_files = self.parser.parse_directory(root, exclude=exclude)
        result.files_scanned = len(parsed_files)

        # Phase 2: Diff — fetch existing file hashes in one query
        existing_files = self.graph.get_code_files(project_id)
        existing_by_path: dict[str, dict] = {ef["path"]: ef for ef in existing_files}

        current_paths: set[str] = set()
        changed_files: list[ParseResult] = []
        all_ok_files: list[ParseResult] = []  # For import resolution (includes skipped)

        for parsed in parsed_files:
            current_paths.add(parsed.file_path)

            if not parsed.ok:
                result.errors.append(f"{parsed.file_path}: {parsed.error}")
                continue

            all_ok_files.append(parsed)
            existing = existing_by_path.get(parsed.file_path)

            if not force and existing and existing.get("content_hash") == parsed.content_hash:
                result.files_skipped += 1
                continue

            changed_files.append(parsed)
            result.files_indexed += 1
            result.symbols_created += len(parsed.symbols)
            result.imports_created += len(parsed.imports)

        # Detect stale files
        stale_uuids = []
        for ef in existing_files:
            if ef["path"] not in current_paths:
                stale_uuids.append(ef["uuid"])
                result.files_deleted += 1

        # Phase 3: Resolve imports, then batch-upsert
        import_edges = _resolve_all_imports(all_ok_files, current_paths)
        file_dicts = [_parsed_to_dict(p) for p in changed_files]

        if file_dicts or stale_uuids or import_edges:
            self.graph.batch_upsert_code_graph(
                project_id=project_id,
                files=file_dicts,
                import_edges=import_edges,
                stale_file_uuids=stale_uuids,
            )

        logger.info("Code index complete for %s: %s", project, result.summary())
        return result


def _parsed_to_dict(parsed: ParseResult) -> dict:
    """Convert a ParseResult into the dict format expected by batch_upsert_code_graph."""
    symbols = []
    for sym in parsed.all_symbols:
        symbols.append({
            "qualified_name": sym.qualified_name,
            "name": sym.name,
            "kind": sym.kind,
            "start_line": sym.start_line,
            "end_line": sym.end_line,
            "signature": sym.signature,
            "docstring": sym.docstring,
            "parent_name": sym.parent_name,
        })
    return {
        "path": parsed.file_path,
        "language": parsed.language,
        "content_hash": parsed.content_hash,
        "symbols": symbols,
    }


def _resolve_all_imports(
    parsed_files: list[ParseResult],
    known_paths: set[str],
) -> list[tuple[str, str]]:
    """Resolve import statements to (importer_path, imported_path) edges."""
    # Detect common root prefix so absolute paths resolve to proper module names.
    # e.g. "/home/user/project/cairn/core/services.py" with root "/home/user/project/"
    #       -> "cairn.core.services" instead of "/.home.user.project.cairn.core.services"
    root_prefix = ""
    if parsed_files:
        sample = parsed_files[0].file_path
        if sample.startswith("/"):
            # Find the common prefix of all file paths
            common = Path(sample).parent
            for p in parsed_files[1:]:
                while not p.file_path.startswith(str(common) + "/") and str(common) != "/":
                    common = common.parent
            # Walk up until we find a directory that isn't a Python package
            # (i.e. has no __init__.py among our known files)
            while str(common) != "/":
                init_path = str(common / "__init__.py")
                if init_path not in known_paths:
                    break
                common = common.parent
            root_prefix = str(common).rstrip("/") + "/"

    def _rel(file_path: str) -> str:
        """Strip root prefix for module resolution."""
        if root_prefix and file_path.startswith(root_prefix):
            return file_path[len(root_prefix):]
        return file_path

    # Build module -> file path mapping (using relative paths for module names)
    module_to_path: dict[str, str] = {}
    for parsed in parsed_files:
        rel = _rel(parsed.file_path)
        mod = path_to_module(rel)
        if mod:
            module_to_path[mod] = parsed.file_path  # Value stays absolute
        ts_mod = path_to_module_ts(rel)
        if ts_mod:
            module_to_path[ts_mod] = parsed.file_path

    edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    # Build Go directory -> file paths mapping for package resolution.
    # Go packages are directories — all .go files in a directory share a package.
    go_dir_to_files: dict[str, list[str]] = {}
    for parsed in parsed_files:
        if parsed.language == "golang":
            dir_path = str(Path(parsed.file_path).parent)
            go_dir_to_files.setdefault(dir_path, []).append(parsed.file_path)

    for parsed in parsed_files:
        is_ts = parsed.language in ("typescript", "typescript_tsx")
        is_go = parsed.language == "golang"

        for imp in parsed.imports:
            target_path = None

            if is_ts:
                import_source = _extract_ts_import_source(imp.name)
                if import_source:
                    importer_dir = str(Path(parsed.file_path).parent)
                    target_path = resolve_ts_import(import_source, importer_dir, known_paths)
            elif is_go:
                target_path = _resolve_go_import(
                    imp.name, parsed.file_path, go_dir_to_files, root_prefix,
                )
            else:
                imported_module = imp.name
                if imported_module.startswith("from "):
                    parts = imported_module.split()
                    if len(parts) >= 2:
                        imported_module = parts[1]
                elif imported_module.startswith("import "):
                    imported_module = imported_module[7:].split(",")[0].strip()

                target_path = module_to_path.get(imported_module)
                if not target_path:
                    for mod, path in module_to_path.items():
                        if imported_module.startswith(mod + ".") or mod.startswith(imported_module + "."):
                            target_path = path
                            break

            if target_path and target_path in known_paths and target_path != parsed.file_path:
                edge = (parsed.file_path, target_path)
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)

    return edges


def _extract_ts_import_source(import_text: str) -> str | None:
    """Extract the module specifier from a TS import statement text.

    e.g. "import { foo } from './utils'" -> "./utils"
         "import React from 'react'" -> "react"
    """
    for quote in ("'", '"'):
        idx = import_text.rfind(f"from {quote}")
        if idx == -1:
            idx = import_text.rfind(f"from{quote}")
        if idx != -1:
            start = import_text.index(quote, idx) + 1
            end = import_text.index(quote, start)
            return import_text[start:end]
    for quote in ("'", '"'):
        if f"import {quote}" in import_text or f"import{quote}" in import_text:
            try:
                start = import_text.index(quote) + 1
                end = import_text.index(quote, start)
                return import_text[start:end]
            except ValueError:
                pass
    return None


def _resolve_go_import(
    import_text: str,
    importer_path: str,
    go_dir_to_files: dict[str, list[str]],
    root_prefix: str,
) -> str | None:
    """Resolve a Go import to a file in the project.

    Go imports are quoted package paths like "fmt" or "github.com/user/repo/pkg".
    We match the import path suffix against known directory paths within the project.
    Returns the first .go file in the matched directory (representing the package).
    """
    # Strip quotes and optional alias prefix (e.g. `mypkg "github.com/..."`)
    text = import_text.strip()
    # Handle aliased imports: `alias "path/to/pkg"`
    if " " in text:
        text = text.split()[-1]
    # Strip quotes
    text = text.strip('"').strip("'")
    if not text:
        return None

    # Try to match the import path suffix against known Go directories
    for dir_path, files in go_dir_to_files.items():
        rel_dir = dir_path
        if root_prefix and dir_path.startswith(root_prefix):
            rel_dir = dir_path[len(root_prefix):]

        # Check if the directory path ends with the import path
        # e.g. import "myproject/pkg/utils" matches dir ".../myproject/pkg/utils"
        if rel_dir == text or rel_dir.endswith("/" + text):
            # Don't resolve to files in the same directory (same package)
            if dir_path == str(Path(importer_path).parent):
                continue
            return files[0] if files else None

    return None
