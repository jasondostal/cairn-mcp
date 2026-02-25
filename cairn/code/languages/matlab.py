"""MATLAB language support for tree-sitter parsing.

Extracts function definitions from MATLAB source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_matlab as tsmatlab

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the MATLAB tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsmatlab.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed MATLAB AST.

    Walks the tree and extracts:
      - Function definitions (function_definition)
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
    """Walk declarations in a MATLAB source file."""
    for child in node.children:
        if child.type == "function_definition":
            _extract_function(child, source, file_path, symbols, parent_name)


# -- Extractors ---------------------------------------------------------------


def _extract_function(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract a function definition."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    kind = "method" if parent_name else "function"
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Build signature from the first line
    output_node = _find_child(node, "function_output")
    args_node = _find_child(node, "function_arguments")

    sig_parts = ["function"]
    if output_node:
        output_text = _node_text(output_node, source).strip()
        sig_parts.append(f"{output_text}")
    sig_parts.append(name)
    if args_node:
        sig_parts.append(_node_text(args_node, source))

    sig = " ".join(sig_parts)

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

    # Walk body for nested functions
    body = _find_child(node, "block")
    if body:
        _walk_node(body, source, file_path, symbols, parent_name=name)


# -- Helpers -------------------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract MATLAB doc comment following the function signature.

    MATLAB uses % comments immediately after the function line.
    """
    # In MATLAB, doc comments come AFTER the function signature, inside the body
    for child in node.children:
        if child.type == "comment":
            text = _node_text(child, source).strip()
            if text.startswith("%"):
                line = text[1:].strip()
                return line or None
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
