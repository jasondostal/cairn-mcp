"""SQL language support for tree-sitter parsing.

Extracts CREATE TABLE, CREATE VIEW, CREATE FUNCTION, CREATE INDEX,
and CREATE TRIGGER statements from SQL source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_sql as tssql

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the SQL tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tssql.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed SQL AST.

    Walks the tree and extracts:
      - CREATE TABLE statements
      - CREATE VIEW statements
      - CREATE FUNCTION statements
      - CREATE INDEX statements
      - CREATE TRIGGER statements
    """
    symbols: list[CodeSymbol] = []
    _walk_node(tree.root_node, source, file_path, symbols)
    return symbols


def _walk_node(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Walk top-level statements in a SQL source file."""
    for child in node.children:
        if child.type == "statement":
            _extract_statement(child, source, file_path, symbols)
        elif child.type in _CREATE_TYPES:
            sym = _extract_create(child, source, file_path)
            if sym:
                symbols.append(sym)


_CREATE_TYPES = {
    "create_table", "create_view", "create_function",
    "create_index", "create_trigger",
}

_KIND_MAP = {
    "create_table": "table",
    "create_view": "view",
    "create_function": "function",
    "create_index": "index",
    "create_trigger": "trigger",
}


def _extract_statement(
    node: ts.Node, source: bytes, file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract CREATE statements from a statement node."""
    for child in node.children:
        if child.type in _CREATE_TYPES:
            sym = _extract_create(child, source, file_path)
            if sym:
                symbols.append(sym)


def _extract_create(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a CREATE statement (table, view, function, index, trigger)."""
    kind = _KIND_MAP.get(node.type)
    if not kind:
        return None

    name = _extract_name(node, source)
    if not name:
        return None

    sig = _node_text(node, source).split("\n")[0].rstrip()

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
    )


def _extract_name(node: ts.Node, source: bytes) -> str | None:
    """Extract the object name from a CREATE statement.

    For CREATE INDEX the name is a direct identifier child (before ON).
    For other CREATE statements the name is in object_reference > identifier.
    """
    # CREATE INDEX has the index name as a direct identifier child
    # (before the ON keyword), while object_reference holds the table name.
    if node.type == "create_index":
        ident = _find_child(node, "identifier")
        if ident:
            return _node_text(ident, source)

    # Most other CREATE statements have object_reference with identifier inside
    obj_ref = _find_child(node, "object_reference")
    if obj_ref:
        ident = _find_child(obj_ref, "identifier")
        if ident:
            return _node_text(ident, source)

    # Fallback: direct identifier child
    ident = _find_child(node, "identifier")
    if ident:
        return _node_text(ident, source)

    return None


# -- Helpers --------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract SQL doc comment preceding a statement.

    SQL uses -- for line comments and /* */ for block comments (marginalia).
    We look at the parent statement's prev_sibling for comments.
    """
    # Try the node itself first, then its parent (statement wrapper)
    target = node
    if node.parent and node.parent.type == "statement":
        target = node.parent

    sibling = target.prev_sibling

    # Block comment (marginalia)
    if sibling and sibling.type == "marginalia":
        text = _node_text(sibling, source).strip()
        if text.startswith("/*") and text.endswith("*/"):
            inner = text[2:-2].strip()
            lines = [line.strip().lstrip("* ").strip() for line in inner.split("\n")]
            return " ".join(l for l in lines if l) or None

    # Line comment
    comments: list[str] = []
    while sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("--"):
            line = text[2:].strip()
            if line:
                comments.append(line)
        sibling = sibling.prev_sibling

    if comments:
        comments.reverse()
        return " ".join(comments)
    return None


def _find_child(node: ts.Node, child_type: str) -> ts.Node | None:
    """Find the first direct child of a given type."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    """Get the text of a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
