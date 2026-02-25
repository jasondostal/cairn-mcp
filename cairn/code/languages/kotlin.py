"""Kotlin language support for tree-sitter parsing.

Extracts classes, objects, interfaces, data classes, functions,
methods, properties, and imports from Kotlin source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_kotlin as tskotlin

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Kotlin tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tskotlin.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Kotlin AST.

    Walks the tree and extracts:
      - Classes, data classes, interfaces (class_declaration)
      - Objects (object_declaration)
      - Functions/methods (function_declaration)
      - Properties (property_declaration)
      - Imports (import)
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
    """Walk declarations in a Kotlin source file."""
    for child in node.children:
        if child.type == "import":
            sym = _extract_import(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "class_declaration":
            _extract_class(child, source, file_path, symbols, parent_name)

        elif child.type == "object_declaration":
            _extract_object(child, source, file_path, symbols, parent_name)

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
    # import node has children: import keyword, qualified_identifier
    qi = _find_child(node, "qualified_identifier")
    if qi:
        text = _node_text(qi, source).strip()
    else:
        # Fallback: extract text after 'import' keyword
        full = _node_text(node, source).strip()
        text = full.replace("import ", "").strip()

    return CodeSymbol(
        name=text,
        qualified_name=text,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"import {text}",
    )


def _extract_class(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract a class, data class, or interface declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Determine kind from children
    kind = "class"
    has_interface = any(c.type == "interface" for c in node.children)
    if has_interface:
        kind = "interface"
    else:
        # Check for data modifier
        modifiers = _find_child(node, "modifiers")
        if modifiers:
            for mod_child in modifiers.children:
                if mod_child.type == "class_modifier":
                    mod_text = _node_text(mod_child, source).strip()
                    if mod_text == "data":
                        kind = "data_class"
                        break

    sig = _node_text(node, source).split("{")[0].strip()
    # For data classes without body, sig is the full text
    if "{" not in _node_text(node, source):
        sig = _node_text(node, source).strip()

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

    # Walk body for members
    body = _find_child(node, "class_body")
    if body:
        _walk_node(body, source, file_path, symbols, parent_name=name)


def _extract_object(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract an object declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("{")[0].strip()

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="object",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    ))

    # Walk body for members
    body = _find_child(node, "class_body")
    if body:
        _walk_node(body, source, file_path, symbols, parent_name=name)


def _extract_function(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a function or method declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    kind = "method" if parent_name else "function"
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Build signature from the declaration up to the body
    full_text = _node_text(node, source)
    sig = full_text.split("{")[0].strip()

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
    """Extract a property declaration (val/var)."""
    # Name is in variable_declaration > identifier, or directly as identifier
    var_decl = _find_child(node, "variable_declaration")
    if var_decl:
        name_node = _find_child(var_decl, "identifier")
    else:
        name_node = _find_child(node, "identifier")

    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("\n")[0].strip()

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="property",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


# -- Helpers -----------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract KDoc comment preceding a declaration.

    Kotlin uses /** ... */ block comments for documentation.
    """
    sibling = node.prev_sibling

    if sibling and sibling.type == "block_comment":
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
