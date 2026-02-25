"""Bash language support for tree-sitter parsing.

Extracts function definitions, variable assignments (exported and local),
and source/. imports from Bash source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_bash as tsbash

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Bash tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsbash.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Bash AST.

    Walks the tree and extracts:
      - Function definitions
      - Exported variable assignments (via export/declare)
      - Top-level variable assignments
      - Source/dot imports
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
    """Walk top-level statements in a Bash source file."""
    for child in node.children:
        if child.type == "function_definition":
            sym = _extract_function(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "declaration_command":
            _extract_declaration(child, source, file_path, symbols)

        elif child.type == "variable_assignment":
            sym = _extract_variable(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "command":
            sym = _extract_source_import(child, source, file_path)
            if sym:
                symbols.append(sym)


# -- Extractors -----------------------------------------------------


def _extract_function(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a function definition."""
    name_node = _find_child(node, "word")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = f"{name}()"

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="function",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
    )


def _extract_declaration(
    node: ts.Node, source: bytes, file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract exported or declared variable assignments.

    Handles `export VAR=val` and `declare` commands.
    """
    is_export = any(
        c.type in ("export", "declare") for c in node.children
    )
    if not is_export:
        return

    for child in node.children:
        if child.type == "variable_assignment":
            var_name_node = _find_child(child, "variable_name")
            if not var_name_node:
                continue

            name = _node_text(var_name_node, source)
            sig = _node_text(node, source).split("\n")[0].rstrip()

            symbols.append(CodeSymbol(
                name=name,
                qualified_name=name,
                kind="variable",
                file_path=file_path,
                start_line=child.start_point.row + 1,
                end_line=child.end_point.row + 1,
                signature=sig,
                docstring=_extract_doc_comment(node, source),
            ))


def _extract_variable(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a top-level variable assignment (non-exported)."""
    var_name_node = _find_child(node, "variable_name")
    if not var_name_node:
        return None

    name = _node_text(var_name_node, source)
    sig = _node_text(node, source).split("\n")[0].rstrip()

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="variable",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
    )


def _extract_source_import(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract source/dot import commands.

    Matches `source <path>` and `. <path>`.
    """
    cmd_name_node = _find_child(node, "command_name")
    if not cmd_name_node:
        return None

    cmd_word = _find_child(cmd_name_node, "word")
    if not cmd_word:
        return None

    cmd_text = _node_text(cmd_word, source)
    if cmd_text not in ("source", "."):
        return None

    # The argument is the next word after command_name
    args = [c for c in node.children if c.type == "word"]
    if not args:
        return None

    path = _node_text(args[0], source)
    sig = _node_text(node, source).strip()

    return CodeSymbol(
        name=path,
        qualified_name=path,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
    )


# -- Helpers --------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Bash doc comment preceding a declaration.

    Bash doc comments are consecutive # line comments immediately
    before the declaration.
    """
    comments: list[str] = []
    sibling = node.prev_sibling

    while sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("#!"):
            # Skip shebang lines
            break
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
