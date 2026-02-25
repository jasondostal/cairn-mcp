"""Swift language support for tree-sitter parsing.

Extracts classes, structs, protocols, enums, functions, methods,
properties, and imports from Swift source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_swift as tsswift

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Swift tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsswift.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Swift AST.

    Walks the tree and extracts:
      - Classes, structs, enums (all class_declaration with different keywords)
      - Protocols (protocol_declaration)
      - Functions (function_declaration at top level)
      - Methods (function_declaration inside a class body)
      - Properties (property_declaration)
      - Imports (import_declaration)
    """
    symbols: list[CodeSymbol] = []
    _walk_node(tree.root_node, source, file_path, symbols, parent_name=None)
    return symbols


def _walk_node(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Walk declarations in a Swift source file."""
    for child in node.children:
        if child.type == "import_declaration":
            sym = _extract_import(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "class_declaration":
            _extract_class_like(child, source, file_path, symbols, parent_name)

        elif child.type == "protocol_declaration":
            _extract_protocol(child, source, file_path, symbols, parent_name)

        elif child.type == "function_declaration":
            sym = _extract_function(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "property_declaration":
            sym = _extract_property(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)


# -- Extractors --------------------------------------------------------


def _extract_import(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an import declaration."""
    # import_declaration has children: import, identifier
    id_node = _find_child(node, "identifier")
    if not id_node:
        return None

    text = _node_text(id_node, source).strip()
    return CodeSymbol(
        name=text,
        qualified_name=text,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"import {text}",
    )


def _extract_class_like(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract a class, struct, or enum declaration.

    In tree-sitter-swift, all three are class_declaration nodes.
    The kind is determined by the keyword child (class, struct, enum).
    """
    # Determine kind from keyword child
    kind = "class"
    for child in node.children:
        if child.type == "struct":
            kind = "struct"
            break
        elif child.type == "enum":
            kind = "enum"
            break
        elif child.type == "class":
            kind = "class"
            break

    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("{")[0].strip()

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    ))

    # Walk the body for methods, properties, nested types
    body = _find_child(node, "class_body") or _find_child(node, "enum_class_body")
    if body:
        _walk_node(body, source, file_path, symbols, parent_name=name)


def _extract_protocol(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract a protocol declaration."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("{")[0].strip()

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="protocol",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    ))

    # Walk protocol body for function declarations
    body = _find_child(node, "protocol_body")
    if body:
        for child in body.children:
            if child.type == "protocol_function_declaration":
                sym = _extract_protocol_method(child, source, file_path, name)
                if sym:
                    symbols.append(sym)


def _extract_protocol_method(
    node: ts.Node, source: bytes, file_path: str, parent_name: str,
) -> CodeSymbol | None:
    """Extract a protocol method declaration."""
    name_node = _find_child(node, "simple_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = _node_text(node, source).strip()

    return CodeSymbol(
        name=name,
        qualified_name=f"{parent_name}.{name}",
        kind="method",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_function(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a function or method declaration."""
    name_node = _find_child(node, "simple_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    kind = "method" if parent_name else "function"
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Build signature from the declaration line (up to the body)
    sig = _node_text(node, source).split("{")[0].strip()

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_property(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a property declaration (var/let)."""
    # The name is in pattern > simple_identifier
    pattern_node = _find_child(node, "pattern")
    if not pattern_node:
        return None

    name_node = _find_child(pattern_node, "simple_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("\n")[0].strip()

    # Determine if var or let
    binding = _find_child(node, "value_binding_pattern")
    prop_kind = "property"

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind=prop_kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


# -- Helpers -----------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Swift doc comment preceding a declaration.

    Swift doc comments are:
      - Consecutive /// line comments
      - A single /** */ block comment (multiline_comment)
    """
    comments: list[str] = []
    sibling = node.prev_sibling

    while sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("///"):
            line = text[3:].strip()
            comments.append(line)
        sibling = sibling.prev_sibling

    if comments:
        comments.reverse()
        return " ".join(comments)

    # Check for block doc comment
    sibling = node.prev_sibling
    if sibling and sibling.type == "multiline_comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("/**") and text.endswith("*/"):
            inner = text[3:-2].strip()
            lines = [l.strip().lstrip("* ").strip() for l in inner.split("\n")]
            return " ".join(l for l in lines if l) or None

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
