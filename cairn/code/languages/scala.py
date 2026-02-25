"""Scala language support for tree-sitter parsing.

Extracts objects, classes, traits, case classes, defs, vals,
and imports from Scala source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_scala as tsscala

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Scala tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsscala.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Scala AST.

    Walks the tree and extracts:
      - Objects (object_definition)
      - Classes and case classes (class_definition)
      - Traits (trait_definition)
      - Functions/methods (function_definition, function_declaration)
      - Vals (val_definition)
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
    """Walk declarations in a Scala source file."""
    for child in node.children:
        if child.type == "import_declaration":
            sym = _extract_import(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "object_definition":
            _extract_object(child, source, file_path, symbols, parent_name)

        elif child.type == "class_definition":
            _extract_class(child, source, file_path, symbols, parent_name)

        elif child.type == "trait_definition":
            _extract_trait(child, source, file_path, symbols, parent_name)

        elif child.type in ("function_definition", "function_declaration"):
            sym = _extract_function(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "val_definition":
            sym = _extract_val(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)


# -- Extractors --------------------------------------------------------


def _extract_import(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an import declaration."""
    # import_declaration children: import, identifier, ., identifier, ...
    # Reconstruct the import path from all non-import children
    parts: list[str] = []
    for child in node.children:
        if child.type == "identifier":
            parts.append(_node_text(child, source))
        elif child.type == ".":
            parts.append(".")

    text = "".join(parts) if parts else _node_text(node, source).replace("import ", "").strip()

    return CodeSymbol(
        name=text,
        qualified_name=text,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"import {text}",
    )


def _extract_object(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract an object definition."""
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
    body = _find_child(node, "template_body")
    if body:
        _walk_node(body, source, file_path, symbols, parent_name=name)


def _extract_class(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract a class or case class definition."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Check if it's a case class
    is_case = any(c.type == "case" for c in node.children)
    kind = "case_class" if is_case else "class"

    sig = _node_text(node, source).split("{")[0].strip()
    # For case classes without body, sig is the full text
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
    body = _find_child(node, "template_body")
    if body:
        _walk_node(body, source, file_path, symbols, parent_name=name)


def _extract_trait(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract a trait definition."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("{")[0].strip()

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="trait",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    ))

    # Walk body for members
    body = _find_child(node, "template_body")
    if body:
        _walk_node(body, source, file_path, symbols, parent_name=name)


def _extract_function(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a function/method definition or declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    kind = "method" if parent_name else "function"
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Build signature up to the body
    full_text = _node_text(node, source)
    sig = full_text.split("{")[0].strip()
    if sig.endswith("="):
        sig = sig[:-1].strip()

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


def _extract_val(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a val definition."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("\n")[0].strip()

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="val",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


# -- Helpers -----------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Scaladoc comment preceding a declaration.

    Scala uses /** ... */ block comments for documentation.
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
