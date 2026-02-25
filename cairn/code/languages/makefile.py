"""Makefile language support for tree-sitter parsing.

Extracts targets, variable assignments, and include directives
from Makefile/GNUMakefile files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_make as tsmake

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Makefile tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsmake.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Makefile AST.

    Walks the tree and extracts:
      - Targets as "target" kind
      - Variable assignments as "variable" kind
      - Include directives as "import" kind
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
    """Walk top-level statements in a Makefile."""
    for child in node.children:
        if child.type == "rule":
            syms = _extract_rule(child, source, file_path)
            symbols.extend(syms)

        elif child.type == "variable_assignment":
            sym = _extract_variable(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "include_directive":
            sym = _extract_include(child, source, file_path)
            if sym:
                symbols.append(sym)


# -- Extractors ---------------------------------------------------------------


def _extract_rule(
    node: ts.Node, source: bytes, file_path: str,
) -> list[CodeSymbol]:
    """Extract target(s) from a Makefile rule."""
    symbols: list[CodeSymbol] = []

    targets_node = _find_child(node, "targets")
    if not targets_node:
        return symbols

    # Build prerequisite list for signature
    prereqs_node = _find_child(node, "prerequisites")
    prereqs = _node_text(prereqs_node, source).strip() if prereqs_node else ""

    for child in targets_node.children:
        if child.type == "word":
            name = _node_text(child, source)
            sig = f"{name}: {prereqs}" if prereqs else f"{name}:"

            symbols.append(CodeSymbol(
                name=name,
                qualified_name=name,
                kind="target",
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                signature=sig,
                docstring=_extract_doc_comment(node, source),
            ))

    return symbols


def _extract_variable(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a variable assignment."""
    name_node = _find_child(node, "word")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = _node_text(node, source).split("\n")[0].strip()

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="variable",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
    )


def _extract_include(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an include directive."""
    list_node = _find_child(node, "list")
    if list_node:
        name = _node_text(list_node, source).strip()
    else:
        full = _node_text(node, source).strip()
        name = full.replace("include", "").strip()

    if not name:
        return None

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"include {name}",
    )


# -- Helpers -------------------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Makefile comment preceding a target.

    Makefile comments are # lines immediately before the rule.
    """
    comments: list[str] = []
    sibling = node.prev_sibling

    while sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("#"):
            line = text[1:].strip()
            if line:
                comments.append(line)
        sibling = sibling.prev_sibling

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
