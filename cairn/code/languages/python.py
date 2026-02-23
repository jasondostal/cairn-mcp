"""Python language support for tree-sitter parsing.

Extracts functions, classes, methods, and imports from Python source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_python as tspython

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Python tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tspython.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Python AST.

    Walks the tree and extracts:
      - Module-level functions
      - Classes (with their methods as children)
      - Module-level imports
      - Module-level constants (ALL_CAPS assignments)
    """
    symbols: list[CodeSymbol] = []
    _walk_node(tree.root_node, source, file_path, parent_name=None, symbols=symbols)
    return symbols


def _walk_node(
    node: ts.Node,
    source: bytes,
    file_path: str,
    parent_name: str | None,
    symbols: list[CodeSymbol],
) -> None:
    """Recursively walk tree-sitter nodes extracting symbols."""
    for child in node.children:
        if child.type == "class_definition":
            sym = _extract_class(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)
                # Extract methods as children
                body = _find_child(child, "block")
                if body:
                    _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)

        elif child.type == "function_definition":
            sym = _extract_function(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "decorated_definition":
            # Unwrap decorator to get the actual definition
            for inner in child.children:
                if inner.type in ("function_definition", "class_definition"):
                    if inner.type == "class_definition":
                        sym = _extract_class(inner, source, file_path, parent_name)
                        if sym:
                            sym = CodeSymbol(
                                name=sym.name,
                                qualified_name=sym.qualified_name,
                                kind=sym.kind,
                                file_path=sym.file_path,
                                start_line=child.start_point.row + 1,  # Use decorator start
                                end_line=sym.end_line,
                                signature=sym.signature,
                                docstring=sym.docstring,
                                parent_name=sym.parent_name,
                            )
                            symbols.append(sym)
                            body = _find_child(inner, "block")
                            if body:
                                _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)
                    else:
                        sym = _extract_function(inner, source, file_path, parent_name)
                        if sym:
                            sym = CodeSymbol(
                                name=sym.name,
                                qualified_name=sym.qualified_name,
                                kind=sym.kind,
                                file_path=sym.file_path,
                                start_line=child.start_point.row + 1,
                                end_line=sym.end_line,
                                signature=sym.signature,
                                docstring=sym.docstring,
                                parent_name=sym.parent_name,
                            )
                            symbols.append(sym)

        elif child.type == "import_statement" and parent_name is None:
            sym = _extract_import(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "import_from_statement" and parent_name is None:
            sym = _extract_import(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "expression_statement" and parent_name is None:
            # Check for module-level constant assignments (ALL_CAPS)
            assign = _find_child(child, "assignment")
            if assign:
                sym = _extract_constant(assign, source, file_path)
                if sym:
                    symbols.append(sym)

        elif child.type == "assignment" and parent_name is None:
            sym = _extract_constant(child, source, file_path)
            if sym:
                symbols.append(sym)


def _extract_function(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None
) -> CodeSymbol | None:
    """Extract a function/method definition."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    params_node = _find_child(node, "parameters")
    params = _node_text(params_node, source) if params_node else "()"

    # Return type annotation
    return_type = ""
    ret_node = _find_child(node, "type")
    if ret_node:
        return_type = f" -> {_node_text(ret_node, source)}"

    kind = "method" if parent_name else "function"
    qualified = f"{parent_name}.{name}" if parent_name else name

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"def {name}{params}{return_type}",
        docstring=_extract_docstring(node, source),
        parent_name=parent_name,
    )


def _extract_class(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None
) -> CodeSymbol | None:
    """Extract a class definition."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)

    # Base classes
    bases = ""
    arg_list = _find_child(node, "argument_list")
    if arg_list:
        bases = _node_text(arg_list, source)

    qualified = f"{parent_name}.{name}" if parent_name else name

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="class",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"class {name}{bases}",
        docstring=_extract_docstring(node, source),
        parent_name=parent_name,
    )


def _extract_import(node: ts.Node, source: bytes, file_path: str) -> CodeSymbol:
    """Extract an import statement."""
    text = _node_text(node, source).strip()
    return CodeSymbol(
        name=text,
        qualified_name=text,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=text,
    )


def _extract_constant(node: ts.Node, source: bytes, file_path: str) -> CodeSymbol | None:
    """Extract a module-level constant (ALL_CAPS identifier)."""
    # First child should be the identifier
    if not node.children:
        return None
    left = node.children[0]
    if left.type != "identifier":
        return None
    name = _node_text(left, source)
    # Only treat ALL_CAPS names as constants
    if not name.isupper() or not name.replace("_", "").isalpha():
        return None
    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="constant",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=_node_text(node, source).split("\n")[0],
    )


# ── Helpers ────────────────────────────────────────────────────


def _find_child(node: ts.Node, child_type: str) -> ts.Node | None:
    """Find the first direct child of a given type."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    """Get the text of a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _extract_docstring(node: ts.Node, source: bytes) -> str | None:
    """Extract docstring from a function/class body."""
    body = _find_child(node, "block")
    if not body or not body.children:
        return None
    first_stmt = body.children[0]
    if first_stmt.type == "expression_statement":
        expr = first_stmt.children[0] if first_stmt.children else None
        if expr and expr.type == "string":
            text = _node_text(expr, source)
            # Strip triple quotes
            for q in ('"""', "'''"):
                if text.startswith(q) and text.endswith(q):
                    return text[3:-3].strip()
            # Single-line string docstring
            for q in ('"', "'"):
                if text.startswith(q) and text.endswith(q):
                    return text[1:-1].strip()
    return None
