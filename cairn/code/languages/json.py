"""JSON language support for tree-sitter parsing.

Extracts top-level object keys as "key" kind symbols from JSON files.
Only first-level keys are extracted; nested objects are not walked.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_json as tsjson

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the JSON tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsjson.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed JSON AST.

    Walks the tree and extracts:
      - Top-level object keys as "key" kind symbols
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
    """Walk the top-level document and extract first-level keys."""
    # JSON AST: document > object > pair*
    # We only want the first-level pairs inside the root object.
    for child in node.children:
        if child.type == "object":
            _extract_object_keys(child, source, file_path, symbols)


# -- Extractors ---------------------------------------------------------------


def _extract_object_keys(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract keys from a top-level JSON object."""
    for child in node.children:
        if child.type == "pair":
            key_node = _find_child(child, "string")
            if not key_node:
                continue

            # The key text is the string_content inside the string node
            content_node = _find_child(key_node, "string_content")
            if not content_node:
                continue

            name = _node_text(content_node, source)
            symbols.append(CodeSymbol(
                name=name,
                qualified_name=name,
                kind="key",
                file_path=file_path,
                start_line=child.start_point.row + 1,
                end_line=child.end_point.row + 1,
                signature=name,
                docstring=None,  # JSON has no comments
            ))


# -- Helpers -------------------------------------------------------------------


def _find_child(node: ts.Node, child_type: str) -> ts.Node | None:
    """Find the first direct child of a given type."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    """Get the text of a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
