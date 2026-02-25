"""HCL (HashiCorp Configuration Language) support for tree-sitter parsing.

Extracts resource, data, variable, output, module, and locals blocks
from Terraform/HCL source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_hcl as tshcl

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the HCL tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tshcl.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed HCL AST.

    Walks the tree and extracts:
      - resource blocks (e.g. resource "aws_vpc" "main")
      - data blocks (e.g. data "aws_ami" "ubuntu")
      - variable blocks
      - output blocks
      - module blocks
      - locals blocks
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
    """Walk the HCL config_file tree.

    The structure is: config_file > body > block(s).
    Each block has an identifier as the first child, followed by
    optional string_lit labels, then a block body in braces.
    """
    # Navigate into body if present
    if node.type == "config_file":
        body = _find_child(node, "body")
        if body:
            _walk_body(body, source, file_path, symbols)
    elif node.type == "body":
        _walk_body(node, source, file_path, symbols)


def _walk_body(
    body: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Walk a body node and extract blocks."""
    for child in body.children:
        if child.type == "block":
            sym = _extract_block(child, source, file_path)
            if sym:
                symbols.append(sym)


# Block type -> symbol kind mapping
_BLOCK_KINDS = {
    "resource": "resource",
    "data": "data",
    "variable": "variable",
    "output": "output",
    "module": "module",
    "locals": "locals",
    "provider": "provider",
    "terraform": "terraform",
}


def _extract_block(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an HCL block (resource, data, variable, etc.).

    Block structure:
      block > identifier string_lit* block_start body block_end
    """
    ident = _find_child(node, "identifier")
    if not ident:
        return None

    block_type = _node_text(ident, source)
    kind = _BLOCK_KINDS.get(block_type)
    if kind is None:
        return None

    # Collect string labels (e.g. "aws_vpc" "main")
    labels = []
    for child in node.children:
        if child.type == "string_lit":
            text = _extract_string_content(child, source)
            if text:
                labels.append(text)

    # Build name and signature
    if kind in ("resource", "data") and len(labels) >= 2:
        name = f"{labels[0]}.{labels[1]}"
        sig = f'{block_type} "{labels[0]}" "{labels[1]}"'
    elif labels:
        name = labels[0]
        sig = f'{block_type} "{labels[0]}"'
    else:
        name = block_type
        sig = block_type

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
    )


# -- Helpers --------------------------------------------------------


def _extract_string_content(node: ts.Node, source: bytes) -> str | None:
    """Extract the text content from a string_lit node (without quotes)."""
    for child in node.children:
        if child.type == "template_literal":
            return _node_text(child, source)
    return None


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract HCL doc comment preceding a block.

    HCL uses # and // for line comments. Comments may be siblings of
    the block within the body, or siblings of the body node itself
    (for the first block in a file, where the comment sits in config_file).
    """
    comments: list[str] = []
    sibling = node.prev_sibling

    # If no prev_sibling and parent is body, check config_file-level comments
    if sibling is None and node.parent and node.parent.type == "body":
        sibling = node.parent.prev_sibling

    while sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("#"):
            line = text[1:].strip()
            if line:
                comments.append(line)
        elif text.startswith("//"):
            line = text[2:].strip()
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
