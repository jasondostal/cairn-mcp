"""Groovy language support for tree-sitter parsing.

Extracts classes, methods, fields, and imports from Groovy source files.
Useful for parsing Jenkinsfiles and Gradle build scripts.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_groovy as tsgroovy

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Groovy tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsgroovy.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Groovy AST.

    Walks the tree and extracts:
      - Classes (class_declaration)
      - Methods (method_declaration)
      - Fields (field_declaration)
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
    """Walk declarations in a Groovy source file."""
    for child in node.children:
        if child.type == "import_declaration":
            sym = _extract_import(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "class_declaration":
            _extract_class(child, source, file_path, symbols, parent_name)

        elif child.type == "method_declaration":
            sym = _extract_method(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "field_declaration":
            sym = _extract_field(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "function_definition":
            sym = _extract_function_def(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)


# -- Extractors ---------------------------------------------------------------


def _extract_import(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an import declaration."""
    # import_declaration > import, scoped_identifier
    scoped = _find_child(node, "scoped_identifier")
    if scoped:
        text = _node_text(scoped, source).strip()
    else:
        full = _node_text(node, source).strip()
        text = full.replace("import ", "").strip().rstrip(";").rstrip()

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
    """Extract a class declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("{")[0].strip()

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="class",
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


def _extract_method(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a method declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    kind = "method" if parent_name else "function"
    qualified = f"{parent_name}.{name}" if parent_name else name

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


def _extract_function_def(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a def-style function definition."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    kind = "method" if parent_name else "function"
    qualified = f"{parent_name}.{name}" if parent_name else name

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


def _extract_field(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a field declaration."""
    var_decl = _find_child(node, "variable_declarator")
    if not var_decl:
        return None

    # variable_declarator contains the name as its first identifier-like child
    name_node = _find_child(var_decl, "identifier")
    if not name_node:
        # The variable_declarator text itself may be "name = value"
        name = _node_text(var_decl, source).split("=")[0].strip()
    else:
        name = _node_text(name_node, source)

    if not name:
        return None

    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("\n")[0].strip()

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="field",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        parent_name=parent_name,
    )


# -- Helpers -------------------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Groovydoc comment preceding a declaration."""
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
