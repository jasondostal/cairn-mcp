"""HTML language support for tree-sitter parsing.

Extracts elements with id/class attributes, script/link imports,
and form elements from HTML files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_html as tshtml

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the HTML tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tshtml.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed HTML AST.

    Walks the tree and extracts:
      - Elements with id attributes as "element" kind
      - Script src and link href as "import" kind
      - Form, input, and other interactive elements
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
    """Recursively walk the HTML AST extracting elements."""
    for child in node.children:
        if child.type == "element":
            _extract_element(child, source, file_path, symbols)
        elif child.type == "script_element":
            sym = _extract_script(child, source, file_path)
            if sym:
                symbols.append(sym)
        elif child.type == "style_element":
            _add_tag_symbol(child, "style", source, file_path, symbols)


def _extract_element(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract an HTML element and recurse into children."""
    start_tag = _find_child(node, "start_tag")
    if not start_tag:
        # Self-closing tag
        start_tag = _find_child(node, "self_closing_tag")
        if not start_tag:
            # Still recurse into children
            _walk_node(node, source, file_path, symbols)
            return

    tag_name = _get_tag_name(start_tag, source)
    if not tag_name:
        _walk_node(node, source, file_path, symbols)
        return

    attrs = _get_attributes(start_tag, source)
    id_attr = attrs.get("id")
    href = attrs.get("href")
    src = attrs.get("src")

    # Elements with id attributes
    if id_attr:
        name = id_attr
        sig = f"<{tag_name} id=\"{id_attr}\">"
        symbols.append(CodeSymbol(
            name=name,
            qualified_name=f"{tag_name}#{id_attr}",
            kind="element",
            file_path=file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            signature=sig,
        ))

    # Link tags with href (stylesheets, etc.)
    if tag_name == "link" and href:
        symbols.append(CodeSymbol(
            name=href,
            qualified_name=href,
            kind="import",
            file_path=file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            signature=f"<link href=\"{href}\">",
        ))

    # Img/source/iframe with src
    if tag_name in ("img", "source", "iframe") and src:
        symbols.append(CodeSymbol(
            name=src,
            qualified_name=src,
            kind="import",
            file_path=file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            signature=f"<{tag_name} src=\"{src}\">",
        ))

    # Recurse into child elements
    _walk_node(node, source, file_path, symbols)


def _extract_script(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a script element with src attribute."""
    start_tag = _find_child(node, "start_tag")
    if not start_tag:
        return None

    attrs = _get_attributes(start_tag, source)
    src = attrs.get("src")
    if not src:
        return None

    return CodeSymbol(
        name=src,
        qualified_name=src,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"<script src=\"{src}\">",
    )


def _add_tag_symbol(
    node: ts.Node,
    tag_name: str,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Add a simple tag-based symbol (style, etc.)."""
    symbols.append(CodeSymbol(
        name=tag_name,
        qualified_name=tag_name,
        kind="element",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"<{tag_name}>",
    ))


# -- Helpers -------------------------------------------------------------------


def _get_tag_name(start_tag: ts.Node, source: bytes) -> str | None:
    """Get the tag name from a start_tag or self_closing_tag node."""
    tag_node = _find_child(start_tag, "tag_name")
    if tag_node:
        return _node_text(tag_node, source).lower()
    return None


def _get_attributes(start_tag: ts.Node, source: bytes) -> dict[str, str]:
    """Extract attribute name-value pairs from a start tag."""
    attrs: dict[str, str] = {}
    for child in start_tag.children:
        if child.type == "attribute":
            name_node = _find_child(child, "attribute_name")
            val_node = _find_child(child, "quoted_attribute_value") or _find_child(child, "attribute_value")
            if name_node and val_node:
                name = _node_text(name_node, source)
                val = _node_text(val_node, source).strip("\"'")
                attrs[name] = val
    return attrs


def _find_child(node: ts.Node, child_type: str) -> ts.Node | None:
    """Find the first direct child of a given type."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    """Get the text of a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
