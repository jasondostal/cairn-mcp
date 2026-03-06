"""Zig language support for tree-sitter parsing.

Extracts functions, structs, enums, constants, and @import
declarations from Zig source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_zig as tszig

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Zig tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tszig.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Zig AST.

    Walks the tree and extracts:
      - Functions (function_declaration)
      - Structs, enums, unions (variable_declaration with struct/enum/union)
      - Constants and variables (variable_declaration)
      - @import() as imports
      - Test declarations
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
    """Walk declarations in a Zig source file."""
    for child in node.children:
        if child.type == "function_declaration":
            sym = _extract_function(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "variable_declaration":
            _extract_variable(child, source, file_path, symbols, parent_name)

        elif child.type == "test_declaration":
            sym = _extract_test(child, source, file_path)
            if sym:
                symbols.append(sym)


# -- Extractors ---------------------------------------------------------------


def _extract_function(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a function declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    kind = "method" if parent_name else "function"
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Build signature
    full_text = _node_text(node, source)
    sig = full_text.split("{")[0].strip()
    # Truncate very long signatures
    if len(sig) > 120:
        sig = sig[:117] + "..."

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


def _extract_variable(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract a variable/constant declaration.

    Handles struct, enum, union, @import, and plain constants.
    """
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Check what's assigned
    struct_node = _find_child(node, "struct_declaration")
    enum_node = _find_child(node, "enum_declaration")
    union_node = _find_child(node, "union_declaration")
    builtin_node = _find_child(node, "builtin_function")

    if struct_node:
        sig = _node_text(node, source).split("{")[0].strip()
        symbols.append(CodeSymbol(
            name=name,
            qualified_name=qualified,
            kind="struct",
            file_path=file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            signature=sig,
            docstring=_extract_doc_comment(node, source),
            parent_name=parent_name,
        ))
        # Walk struct body for methods
        for child in struct_node.children:
            if child.type == "function_declaration":
                sym = _extract_function(child, source, file_path, parent_name=name)
                if sym:
                    symbols.append(sym)

    elif enum_node:
        sig = _node_text(node, source).split("{")[0].strip()
        symbols.append(CodeSymbol(
            name=name,
            qualified_name=qualified,
            kind="enum",
            file_path=file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            signature=sig,
            docstring=_extract_doc_comment(node, source),
            parent_name=parent_name,
        ))

    elif union_node:
        sig = _node_text(node, source).split("{")[0].strip()
        symbols.append(CodeSymbol(
            name=name,
            qualified_name=qualified,
            kind="union",
            file_path=file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            signature=sig,
            docstring=_extract_doc_comment(node, source),
            parent_name=parent_name,
        ))

    elif builtin_node and _is_import(builtin_node, source):
        # @import("module")
        mod_name = _extract_import_name(builtin_node, source)
        if mod_name:
            symbols.append(CodeSymbol(
                name=mod_name,
                qualified_name=mod_name,
                kind="import",
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                signature=_node_text(node, source).split(";")[0].strip(),
            ))

    else:
        # Plain constant/variable
        is_const = any(c.type == "const" for c in node.children)
        kind = "constant" if is_const else "variable"
        sig = _node_text(node, source).split(";")[0].strip()
        if len(sig) > 120:
            sig = sig[:117] + "..."

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


def _extract_test(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a test declaration."""
    full_text = _node_text(node, source)
    # Test name is a string literal after 'test'
    sig = full_text.split("{")[0].strip()
    # Extract name from quotes
    name = sig.replace("test", "").strip().strip("\"")
    if not name:
        name = "unnamed_test"

    return CodeSymbol(
        name=name,
        qualified_name=f"test.{name}",
        kind="test",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
    )


# -- Helpers -------------------------------------------------------------------


def _is_import(builtin_node: ts.Node, source: bytes) -> bool:
    """Check if a builtin_function node is @import."""
    bi = _find_child(builtin_node, "builtin_identifier")
    if bi:
        return _node_text(bi, source) == "@import"
    return False


def _extract_import_name(builtin_node: ts.Node, source: bytes) -> str | None:
    """Extract the module name from @import("name")."""
    args = _find_child(builtin_node, "arguments")
    if not args:
        return None

    for child in args.children:
        if child.type in ("string_literal", "string"):
            content = _find_child(child, "string_content")
            if content:
                return _node_text(content, source)
            # Fallback: strip quotes
            text = _node_text(child, source).strip("\"")
            return text
    return None


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Zig doc comment preceding a declaration.

    Zig uses /// line comments for documentation.
    """
    comments: list[str] = []
    sibling = node.prev_sibling

    while sibling and sibling.type == "doc_comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("///"):
            line = text[3:].strip()
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
