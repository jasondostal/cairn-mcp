"""YAML language support for tree-sitter parsing.

Extracts top-level mapping keys as "key" kind symbols from YAML files.
Only first-level keys in the root mapping are extracted.
Comments preceding a key (using #) are captured as docstrings.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_yaml as tsyaml

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the YAML tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsyaml.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed YAML AST.

    Walks the tree and extracts:
      - Top-level mapping keys as "key" kind symbols
      - Comments preceding keys as docstrings
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
    """Walk the YAML AST to find the root block_mapping.

    YAML AST structure: stream > document > block_node > block_mapping > block_mapping_pair*
    """
    for child in node.children:
        if child.type == "document":
            _walk_node(child, source, file_path, symbols)
        elif child.type == "block_node":
            _walk_node(child, source, file_path, symbols)
        elif child.type == "block_mapping":
            _extract_mapping_keys(child, source, file_path, symbols)


# -- Extractors ---------------------------------------------------------------


def _extract_mapping_keys(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract first-level keys from a YAML block_mapping."""
    for child in node.children:
        if child.type == "block_mapping_pair":
            # The key is the first flow_node child
            key_node = _find_child(child, "flow_node")
            if not key_node:
                continue

            name = _node_text(key_node, source).strip()
            if not name:
                continue

            symbols.append(CodeSymbol(
                name=name,
                qualified_name=name,
                kind="key",
                file_path=file_path,
                start_line=child.start_point.row + 1,
                end_line=child.end_point.row + 1,
                signature=name,
                docstring=_extract_doc_comment(child, source),
            ))


# -- Helpers -------------------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract YAML comment preceding a mapping pair.

    YAML comments use # and may appear as direct sibling 'comment' nodes
    or get nested inside the previous sibling's value subtree (e.g. as
    trailing children of a block_sequence). We use a line-based approach:
    scan source lines immediately before the node for # comment lines.
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
