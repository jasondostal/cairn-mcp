"""Markdown language support for tree-sitter parsing.

Extracts ATX headings (# style) as "heading" kind symbols from Markdown files.
The heading signature includes the marker (e.g. "## Section Name").
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_markdown as tsmd

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Markdown tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsmd.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Markdown AST.

    Walks the tree and extracts:
      - ATX headings as "heading" kind symbols
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
    """Recursively walk the Markdown AST looking for atx_heading nodes.

    Markdown AST: document > section* > (atx_heading | section | ...)*
    Sections nest, so we recurse into them.
    """
    for child in node.children:
        if child.type == "atx_heading":
            sym = _extract_heading(child, source, file_path)
            if sym:
                symbols.append(sym)
        elif child.type == "section":
            _walk_node(child, source, file_path, symbols)


# -- Extractors ---------------------------------------------------------------


def _extract_heading(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an ATX heading."""
    # atx_heading children: atx_h{N}_marker, inline
    marker_node = None
    inline_node = None

    for child in node.children:
        if child.type.startswith("atx_h") and child.type.endswith("_marker"):
            marker_node = child
        elif child.type == "inline":
            inline_node = child

    if not inline_node:
        return None

    name = _node_text(inline_node, source).strip()
    if not name:
        return None

    marker = _node_text(marker_node, source) if marker_node else "#"
    sig = f"{marker} {name}"

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="heading",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.start_point.row + 1,
        signature=sig,
        docstring=None,  # Markdown has no doc comments
    )


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
