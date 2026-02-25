"""Lua language support for tree-sitter parsing.

Extracts global and local function declarations, module-level variables,
and require() imports from Lua source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_lua as tslua

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Lua tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tslua.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Lua AST.

    Walks the tree and extracts:
      - Global and local function declarations
      - Module-level variable assignments
      - require() imports
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
    """Walk top-level statements in a Lua source file."""
    for child in node.children:
        if child.type == "function_declaration":
            sym = _extract_function(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "variable_declaration":
            _extract_variable_decl(child, source, file_path, symbols)

        elif child.type == "assignment_statement":
            _extract_assignment(child, source, file_path, symbols)


# -- Extractors ---------------------------------------------------------------


def _extract_function(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a function declaration (global or local)."""
    is_local = any(c.type == "local" for c in node.children)

    # Name can be identifier, dot_index_expression (M.func), or method_index_expression (M:func)
    name_node = (
        _find_child(node, "identifier")
        or _find_child(node, "dot_index_expression")
        or _find_child(node, "method_index_expression")
    )
    if not name_node:
        return None

    name = _node_text(name_node, source)

    # Build signature
    params_node = _find_child(node, "parameters")
    params = _node_text(params_node, source) if params_node else "()"
    prefix = "local function" if is_local else "function"
    sig = f"{prefix} {name}{params}"

    # Determine if it's a method (M:func or M.func)
    kind = "function"
    parent_name = None
    if name_node.type in ("dot_index_expression", "method_index_expression"):
        kind = "method"
        # Parent is the table name (first child)
        if name_node.children:
            parent_name = _node_text(name_node.children[0], source)

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_variable_decl(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract a local variable declaration, including require() imports."""
    assign = _find_child(node, "assignment_statement")
    if not assign:
        return

    # Check for require() on the right-hand side
    expr_list = _find_child(assign, "expression_list")
    if expr_list:
        call = _find_child(expr_list, "function_call")
        if call and _is_require_call(call, source):
            sym = _extract_require(node, assign, call, source, file_path)
            if sym:
                symbols.append(sym)
                return

    # Regular variable assignment
    var_list = _find_child(assign, "variable_list")
    if not var_list:
        return

    for child in var_list.children:
        if child.type == "identifier":
            name = _node_text(child, source)
            sig = _node_text(node, source).split("\n")[0].strip()
            symbols.append(CodeSymbol(
                name=name,
                qualified_name=name,
                kind="variable",
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                signature=sig,
            ))


def _extract_assignment(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract a top-level global assignment."""
    var_list = _find_child(node, "variable_list")
    if not var_list:
        return

    for child in var_list.children:
        if child.type == "identifier":
            name = _node_text(child, source)
            sig = _node_text(node, source).split("\n")[0].strip()
            symbols.append(CodeSymbol(
                name=name,
                qualified_name=name,
                kind="variable",
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                signature=sig,
            ))


def _extract_require(
    decl_node: ts.Node,
    assign_node: ts.Node,
    call_node: ts.Node,
    source: bytes,
    file_path: str,
) -> CodeSymbol | None:
    """Extract a require() import."""
    # Get the module name from the require argument
    args = _find_child(call_node, "arguments")
    if not args:
        return None

    # Find the string argument
    for child in args.children:
        if child.type == "string":
            content = _find_child(child, "string_content")
            if content:
                mod_name = _node_text(content, source)
                sig = _node_text(decl_node, source).split("\n")[0].strip()
                return CodeSymbol(
                    name=mod_name,
                    qualified_name=mod_name,
                    kind="import",
                    file_path=file_path,
                    start_line=decl_node.start_point.row + 1,
                    end_line=decl_node.end_point.row + 1,
                    signature=sig,
                )
    return None


def _is_require_call(call_node: ts.Node, source: bytes) -> bool:
    """Check if a function_call node is a require() call."""
    name_node = _find_child(call_node, "identifier")
    if name_node and _node_text(name_node, source) == "require":
        return True
    return False


# -- Helpers -------------------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Lua doc comment preceding a declaration.

    Lua doc comments are consecutive -- line comments immediately
    before the declaration.
    """
    comments: list[str] = []
    sibling = node.prev_sibling

    while sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("--"):
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
