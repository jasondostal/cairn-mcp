"""CSS language support for tree-sitter parsing.

Extracts selectors (class, ID, tag), @import statements,
@media queries, @keyframes, and CSS custom properties from CSS files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_css as tscss

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the CSS tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tscss.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed CSS AST.

    Walks the tree and extracts:
      - Rule set selectors as "selector" kind
      - @import statements as "import" kind
      - @media queries as "media" kind
      - @keyframes as "keyframes" kind
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
    """Walk top-level statements in a CSS stylesheet."""
    for child in node.children:
        if child.type == "rule_set":
            sym = _extract_rule_set(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "import_statement":
            sym = _extract_import(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "media_statement":
            sym = _extract_media(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "keyframes_statement":
            sym = _extract_keyframes(child, source, file_path)
            if sym:
                symbols.append(sym)


# -- Extractors ---------------------------------------------------------------


def _extract_rule_set(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a CSS rule set (selector + block)."""
    selectors_node = _find_child(node, "selectors")
    if not selectors_node:
        return None

    selector_text = _node_text(selectors_node, source).strip()
    if not selector_text:
        return None

    return CodeSymbol(
        name=selector_text,
        qualified_name=selector_text,
        kind="selector",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=selector_text,
    )


def _extract_import(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a CSS @import statement."""
    full_text = _node_text(node, source).strip().rstrip(";").strip()
    # Extract the URL/path from the import
    name = full_text.replace("@import", "").strip()
    # Clean up url() wrapper and quotes
    if name.startswith("url("):
        name = name[4:].rstrip(")")
    name = name.strip("\"'")

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=full_text,
    )


def _extract_media(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a @media query."""
    # Build the media query signature from the node text up to the block
    full_text = _node_text(node, source)
    sig = full_text.split("{")[0].strip()
    name = sig.replace("@media", "").strip()

    return CodeSymbol(
        name=name or "@media",
        qualified_name=sig,
        kind="media",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
    )


def _extract_keyframes(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a @keyframes declaration."""
    name_node = _find_child(node, "keyframes_name")
    if not name_node:
        return None

    name = _node_text(name_node, source).strip()
    sig = f"@keyframes {name}"

    return CodeSymbol(
        name=name,
        qualified_name=sig,
        kind="keyframes",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
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
