"""TOML language support for tree-sitter parsing.

Extracts tables (sections like [section]) as "table" kind, arrays of tables
([[section]]) as "table" kind, and top-level key-value pairs as "key" kind
from TOML files. Comments preceding declarations are captured as docstrings.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_toml as tstoml

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the TOML tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tstoml.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed TOML AST.

    Walks the tree and extracts:
      - Tables ([section]) as "table" kind
      - Arrays of tables ([[section]]) as "table" kind
      - Top-level key-value pairs as "key" kind
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
    """Walk the top-level TOML document.

    TOML AST: document > (pair | table | table_array_element | comment)*
    """
    for child in node.children:
        if child.type == "pair":
            sym = _extract_pair(child, source, file_path)
            if sym:
                symbols.append(sym)
        elif child.type == "table":
            sym = _extract_table(child, source, file_path)
            if sym:
                symbols.append(sym)
        elif child.type == "table_array_element":
            sym = _extract_table_array(child, source, file_path)
            if sym:
                symbols.append(sym)


# -- Extractors ---------------------------------------------------------------


def _extract_pair(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a top-level key-value pair."""
    key_node = _find_child(node, "bare_key")
    if not key_node:
        # Try dotted_key for keys like a.b = "val"
        key_node = _find_child(node, "dotted_key")
    if not key_node:
        return None

    name = _node_text(key_node, source)
    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="key",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=_node_text(node, source).split("\n")[0].rstrip(),
        docstring=_extract_doc_comment(node, source),
    )


def _extract_table(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a TOML table ([section])."""
    # Table children: [ bare_key ] pair* (or dotted_key)
    key_node = _find_child(node, "bare_key")
    if not key_node:
        key_node = _find_child(node, "dotted_key")
    if not key_node:
        return None

    name = _node_text(key_node, source)
    sig = f"[{name}]"

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="table",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
    )


def _extract_table_array(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a TOML array of tables ([[section]])."""
    key_node = _find_child(node, "bare_key")
    if not key_node:
        key_node = _find_child(node, "dotted_key")
    if not key_node:
        return None

    name = _node_text(key_node, source)
    sig = f"[[{name}]]"

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="table",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
    )


# -- Helpers -------------------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract TOML comment preceding a declaration.

    TOML comments use # and may appear as direct sibling 'comment' nodes
    or get nested inside the previous sibling (e.g. as trailing children
    of a table). We use a line-based approach: scan source lines
    immediately before the node for # comment lines.
    """
    lines = source.decode("utf-8", errors="replace").split("\n")
    start_line = node.start_point.row  # 0-based

    comments: list[str] = []
    idx = start_line - 1
    while idx >= 0:
        stripped = lines[idx].strip()
        if stripped.startswith("#"):
            line = stripped.lstrip("#").strip()
            comments.append(line)
            idx -= 1
        elif stripped == "":
            # Allow one blank line between comment and declaration
            break
        else:
            break

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
