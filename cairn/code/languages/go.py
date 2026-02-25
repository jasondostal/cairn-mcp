"""Go language support for tree-sitter parsing.

Extracts functions, methods, structs, interfaces, type aliases,
constants, variables, and imports from Go source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_go as tsgo

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Go tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsgo.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Go AST.

    Walks the tree and extracts:
      - Package-level functions
      - Methods (with receiver type as parent)
      - Structs and interfaces (from type declarations)
      - Type aliases
      - Constants and variables
      - Import declarations
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
    """Walk top-level declarations in a Go source file."""
    for child in node.children:
        if child.type == "function_declaration":
            sym = _extract_function(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "method_declaration":
            sym = _extract_method(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "type_declaration":
            _extract_type_decl(child, source, file_path, symbols)

        elif child.type == "const_declaration":
            _extract_const_or_var(child, source, file_path, "constant", symbols)

        elif child.type == "var_declaration":
            _extract_const_or_var(child, source, file_path, "variable", symbols)

        elif child.type == "import_declaration":
            _extract_imports(child, source, file_path, symbols)


# ── Extractors ─────────────────────────────────────────────────


def _extract_function(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a top-level function declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    params = _extract_params(node, source)
    result_type = _extract_result(node, source)

    sig = f"func {name}{params}"
    if result_type:
        sig += f" {result_type}"

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


def _extract_method(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a method declaration (function with receiver)."""
    name_node = _find_child(node, "field_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    receiver_type = _extract_receiver_type(node, source)

    # For methods, params are the second parameter_list (first is receiver)
    param_lists = [c for c in node.children if c.type == "parameter_list"]
    params = _node_text(param_lists[1], source) if len(param_lists) >= 2 else "()"
    result_type = _extract_method_result(node, source)

    sig = f"func ({receiver_type}) {name}{params}"
    if result_type:
        sig += f" {result_type}"

    return CodeSymbol(
        name=name,
        qualified_name=f"{receiver_type}.{name}" if receiver_type else name,
        kind="method",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=receiver_type,
    )


def _extract_type_decl(
    node: ts.Node, source: bytes, file_path: str, symbols: list[CodeSymbol],
) -> None:
    """Extract type declarations (struct, interface, alias).

    Handles both single (`type Foo struct{...}`) and grouped
    (`type ( Foo struct{...}; Bar int )`) declarations.
    """
    for child in node.children:
        if child.type == "type_spec":
            sym = _extract_type_spec(child, source, file_path, node)
            if sym:
                symbols.append(sym)
        elif child.type == "type_alias":
            sym = _extract_type_alias(child, source, file_path, node)
            if sym:
                symbols.append(sym)


def _extract_type_spec(
    spec: ts.Node, source: bytes, file_path: str, decl_node: ts.Node,
) -> CodeSymbol | None:
    """Extract a single type_spec from a type declaration."""
    name_node = _find_child(spec, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)

    # Determine kind from the type body
    kind = "type_alias"
    type_body = None
    for child in spec.children:
        if child.type == "struct_type":
            kind = "struct"
            type_body = child
            break
        elif child.type == "interface_type":
            kind = "interface"
            type_body = child
            break

    sig_text = _node_text(spec, source).split("\n")[0].rstrip()
    sig = f"type {sig_text}" if not sig_text.startswith("type") else sig_text

    # For grouped type decls, doc comment is on the spec; for single, on the decl
    doc = _extract_doc_comment(spec, source) or _extract_doc_comment(decl_node, source)

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind=kind,
        file_path=file_path,
        start_line=spec.start_point.row + 1,
        end_line=spec.end_point.row + 1,
        signature=sig,
        docstring=doc,
    )


def _extract_type_alias(
    node: ts.Node, source: bytes, file_path: str, decl_node: ts.Node,
) -> CodeSymbol | None:
    """Extract a type alias (e.g. `type ID = string`)."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig_text = _node_text(node, source).split("\n")[0].rstrip()
    sig = f"type {sig_text}" if not sig_text.startswith("type") else sig_text
    doc = _extract_doc_comment(node, source) or _extract_doc_comment(decl_node, source)

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="type_alias",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=doc,
    )


def _extract_const_or_var(
    node: ts.Node, source: bytes, file_path: str,
    kind: str, symbols: list[CodeSymbol],
) -> None:
    """Extract const or var declarations (single and grouped)."""
    for child in node.children:
        if child.type in ("const_spec", "var_spec"):
            name_node = _find_child(child, "identifier")
            if not name_node:
                continue

            name = _node_text(name_node, source)
            sig = _node_text(child, source).split("\n")[0].rstrip()

            symbols.append(CodeSymbol(
                name=name,
                qualified_name=name,
                kind=kind,
                file_path=file_path,
                start_line=child.start_point.row + 1,
                end_line=child.end_point.row + 1,
                signature=sig,
                docstring=_extract_doc_comment(child, source) or _extract_doc_comment(node, source),
            ))


def _extract_imports(
    node: ts.Node, source: bytes, file_path: str, symbols: list[CodeSymbol],
) -> None:
    """Extract import declarations (single and grouped)."""
    for child in node.children:
        if child.type == "import_spec":
            text = _node_text(child, source).strip()
            symbols.append(CodeSymbol(
                name=text,
                qualified_name=text,
                kind="import",
                file_path=file_path,
                start_line=child.start_point.row + 1,
                end_line=child.end_point.row + 1,
                signature=text,
            ))
        elif child.type == "import_spec_list":
            for spec in child.children:
                if spec.type == "import_spec":
                    text = _node_text(spec, source).strip()
                    symbols.append(CodeSymbol(
                        name=text,
                        qualified_name=text,
                        kind="import",
                        file_path=file_path,
                        start_line=spec.start_point.row + 1,
                        end_line=spec.end_point.row + 1,
                        signature=text,
                    ))
        elif child.type == "interpreted_string_literal":
            # Single import without parens: import "fmt"
            text = _node_text(child, source).strip()
            symbols.append(CodeSymbol(
                name=text,
                qualified_name=text,
                kind="import",
                file_path=file_path,
                start_line=child.start_point.row + 1,
                end_line=child.end_point.row + 1,
                signature=text,
            ))


# ── Helpers ────────────────────────────────────────────────────


def _extract_params(node: ts.Node, source: bytes) -> str:
    """Extract the parameter list text from a function/method."""
    params_node = _find_child(node, "parameter_list")
    return _node_text(params_node, source) if params_node else "()"


def _extract_result(node: ts.Node, source: bytes) -> str:
    """Extract the result/return type from a function declaration.

    For functions: children are func, identifier, parameter_list (params),
    then optionally result type or result parameter_list, then block.
    """
    _TYPE_NODES = {
        "type_identifier", "pointer_type", "slice_type", "map_type",
        "array_type", "qualified_type", "channel_type", "function_type",
        "struct_type", "interface_type",
    }
    # For functions, result comes after the single parameter_list
    found_params = False
    for child in node.children:
        if child.type == "parameter_list":
            found_params = True
            continue
        if found_params:
            if child.type in _TYPE_NODES:
                return _node_text(child, source)
            if child.type == "parameter_list":
                # Multiple return values: (int, error)
                return _node_text(child, source)
    return ""


def _extract_method_result(node: ts.Node, source: bytes) -> str:
    """Extract the result/return type from a method declaration.

    For methods: children are func, parameter_list (receiver),
    field_identifier, parameter_list (params), then optionally result.
    """
    _TYPE_NODES = {
        "type_identifier", "pointer_type", "slice_type", "map_type",
        "array_type", "qualified_type", "channel_type", "function_type",
        "struct_type", "interface_type",
    }
    # Skip past the second parameter_list (params), then look for result
    param_count = 0
    for child in node.children:
        if child.type == "parameter_list":
            param_count += 1
            continue
        if param_count >= 2:
            if child.type in _TYPE_NODES:
                return _node_text(child, source)
            if child.type == "parameter_list":
                return _node_text(child, source)
    return ""


def _extract_receiver_type(node: ts.Node, source: bytes) -> str:
    """Extract the receiver type name from a method declaration.

    Handles both value receivers `(s Server)` and pointer receivers `(s *Server)`.
    Returns just the type name (e.g. "Server").
    """
    param_list = _find_child(node, "parameter_list")
    if not param_list:
        return ""

    for child in param_list.children:
        if child.type == "parameter_declaration":
            # Look for type_identifier or pointer_type containing type_identifier
            for part in child.children:
                if part.type == "type_identifier":
                    return _node_text(part, source)
                if part.type == "pointer_type":
                    inner = _find_child(part, "type_identifier")
                    if inner:
                        return _node_text(inner, source)
    return ""


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Go doc comment preceding a declaration.

    Go doc comments are consecutive // line comments immediately
    before the declaration, or a single /* */ block comment.
    """
    comments: list[str] = []
    sibling = node.prev_sibling

    while sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("//"):
            line = text[2:].strip()
            comments.append(line)
        elif text.startswith("/*") and text.endswith("*/"):
            # Block comment
            inner = text[2:-2].strip()
            lines = [l.strip().lstrip("* ").strip() for l in inner.split("\n")]
            return " ".join(l for l in lines if l) or None
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
