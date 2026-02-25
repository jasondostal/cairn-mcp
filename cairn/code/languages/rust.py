"""Rust language support for tree-sitter parsing.

Extracts functions, methods, structs, enums, traits, impl blocks,
constants, statics, type aliases, modules, and use statements
from Rust source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_rust as tsrust

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Rust tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsrust.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Rust AST."""
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
    """Walk tree-sitter nodes extracting symbols."""
    for child in node.children:
        if child.type == "function_item":
            sym = _extract_function(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "struct_item":
            sym = _extract_struct(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "enum_item":
            sym = _extract_enum(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "trait_item":
            sym = _extract_trait(child, source, file_path)
            if sym:
                symbols.append(sym)
                # Extract method signatures inside the trait
                decl_list = _find_child(child, "declaration_list")
                if decl_list:
                    _walk_trait_body(decl_list, source, file_path, sym.name, symbols)

        elif child.type == "impl_item":
            _extract_impl(child, source, file_path, symbols)

        elif child.type == "const_item":
            sym = _extract_const_or_static(child, source, file_path, "constant")
            if sym:
                symbols.append(sym)

        elif child.type == "static_item":
            sym = _extract_const_or_static(child, source, file_path, "static")
            if sym:
                symbols.append(sym)

        elif child.type == "type_item":
            sym = _extract_type_alias(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "use_declaration":
            sym = _extract_use(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "mod_item":
            sym = _extract_mod(child, source, file_path)
            if sym:
                symbols.append(sym)
                # Extract items inside inline modules
                decl_list = _find_child(child, "declaration_list")
                if decl_list:
                    _walk_node(decl_list, source, file_path, parent_name=sym.name, symbols=symbols)


# ── Extractors ─────────────────────────────────────────────────


def _extract_function(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a function item."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    params = _node_text(_find_child(node, "parameters"), source) if _find_child(node, "parameters") else "()"

    # Return type
    return_type = ""
    for i, child in enumerate(node.children):
        if child.type == "->":
            # Next non-whitespace child is the return type
            for j in range(i + 1, len(node.children)):
                if node.children[j].type not in ("->", "block", "{", "}"):
                    return_type = _node_text(node.children[j], source)
                    break
            break

    kind = "method" if parent_name else "function"
    qualified = f"{parent_name}.{name}" if parent_name else name

    sig = f"fn {name}{params}"
    if return_type:
        sig += f" -> {return_type}"

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


def _extract_struct(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a struct item."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    type_params = _find_child(node, "type_parameters")
    tp = _node_text(type_params, source) if type_params else ""

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="struct",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"struct {name}{tp}",
        docstring=_extract_doc_comment(node, source),
    )


def _extract_enum(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an enum item."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    type_params = _find_child(node, "type_parameters")
    tp = _node_text(type_params, source) if type_params else ""

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="enum",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"enum {name}{tp}",
        docstring=_extract_doc_comment(node, source),
    )


def _extract_trait(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a trait item."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    type_params = _find_child(node, "type_parameters")
    tp = _node_text(type_params, source) if type_params else ""

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="trait",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"trait {name}{tp}",
        docstring=_extract_doc_comment(node, source),
    )


def _walk_trait_body(
    decl_list: ts.Node, source: bytes, file_path: str,
    trait_name: str, symbols: list[CodeSymbol],
) -> None:
    """Extract function signatures from a trait body."""
    for child in decl_list.children:
        if child.type == "function_signature_item":
            sym = _extract_function_signature(child, source, file_path, trait_name)
            if sym:
                symbols.append(sym)
        elif child.type == "function_item":
            sym = _extract_function(child, source, file_path, trait_name)
            if sym:
                symbols.append(sym)


def _extract_function_signature(
    node: ts.Node, source: bytes, file_path: str, parent_name: str,
) -> CodeSymbol | None:
    """Extract a function signature (trait method without body)."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    params = _node_text(_find_child(node, "parameters"), source) if _find_child(node, "parameters") else "()"

    return_type = ""
    for i, child in enumerate(node.children):
        if child.type == "->":
            for j in range(i + 1, len(node.children)):
                if node.children[j].type not in ("->", ";"):
                    return_type = _node_text(node.children[j], source)
                    break
            break

    sig = f"fn {name}{params}"
    if return_type:
        sig += f" -> {return_type}"

    return CodeSymbol(
        name=name,
        qualified_name=f"{parent_name}.{name}",
        kind="method",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_impl(
    node: ts.Node, source: bytes, file_path: str, symbols: list[CodeSymbol],
) -> None:
    """Extract methods from an impl block."""
    # Find the type being implemented
    impl_type = None
    for child in node.children:
        if child.type == "type_identifier":
            impl_type = _node_text(child, source)
            break
        if child.type == "generic_type":
            ti = _find_child(child, "type_identifier")
            if ti:
                impl_type = _node_text(ti, source)
            break

    if not impl_type:
        return

    decl_list = _find_child(node, "declaration_list")
    if decl_list:
        for child in decl_list.children:
            if child.type == "function_item":
                sym = _extract_function(child, source, file_path, impl_type)
                if sym:
                    symbols.append(sym)


def _extract_const_or_static(
    node: ts.Node, source: bytes, file_path: str, kind: str,
) -> CodeSymbol | None:
    """Extract a const or static item."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = _node_text(node, source).split("\n")[0].rstrip().rstrip(";").rstrip()

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


def _extract_type_alias(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a type alias."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = _node_text(node, source).split("\n")[0].rstrip().rstrip(";").rstrip()

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="type_alias",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
    )


def _extract_use(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol:
    """Extract a use declaration."""
    text = _node_text(node, source).strip().rstrip(";").strip()
    return CodeSymbol(
        name=text,
        qualified_name=text,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=text,
    )


def _extract_mod(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a module declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="module",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"mod {name}",
        docstring=_extract_doc_comment(node, source),
    )


# ── Helpers ────────────────────────────────────────────────────


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Rust doc comment (/// or //!) preceding a node."""
    comments: list[str] = []
    sibling = node.prev_sibling

    while sibling and sibling.type == "line_comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("///"):
            line = text[3:].strip()
            comments.append(line)
        elif text.startswith("//!"):
            line = text[3:].strip()
            comments.append(line)
        else:
            break  # Non-doc comment breaks the chain
        sibling = sibling.prev_sibling

    if comments:
        comments.reverse()
        return " ".join(comments)

    # Check for block doc comment /** ... */
    if node.prev_sibling and node.prev_sibling.type == "block_comment":
        text = _node_text(node.prev_sibling, source).strip()
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
