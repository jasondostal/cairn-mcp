"""C++ language support for tree-sitter parsing.

Extracts classes, structs, namespaces, functions, methods,
templates, enums, and includes from C++ source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_cpp as tscpp

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the C++ tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tscpp.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed C++ AST."""
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
        if child.type == "function_definition":
            sym = _extract_function(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "declaration":
            _extract_from_declaration(child, source, file_path, parent_name, symbols)

        elif child.type == "class_specifier":
            sym = _extract_class_or_struct(child, source, file_path, parent_name, "class")
            if sym:
                symbols.append(sym)
                _walk_class_body(child, source, file_path, sym.name, symbols)

        elif child.type == "struct_specifier":
            sym = _extract_class_or_struct(child, source, file_path, parent_name, "struct")
            if sym:
                symbols.append(sym)
                _walk_class_body(child, source, file_path, sym.name, symbols)

        elif child.type == "enum_specifier":
            sym = _extract_enum(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "namespace_definition":
            sym = _extract_namespace(child, source, file_path)
            if sym:
                symbols.append(sym)
                decl_list = _find_child(child, "declaration_list")
                if decl_list:
                    _walk_node(decl_list, source, file_path, parent_name=sym.name, symbols=symbols)

        elif child.type == "template_declaration":
            _extract_template(child, source, file_path, parent_name, symbols)

        elif child.type == "preproc_include":
            sym = _extract_include(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "type_definition":
            sym = _extract_typedef(child, source, file_path)
            if sym:
                symbols.append(sym)


def _walk_class_body(
    class_node: ts.Node, source: bytes, file_path: str,
    class_name: str, symbols: list[CodeSymbol],
) -> None:
    """Extract method declarations and nested types from a class/struct body."""
    body = _find_child(class_node, "field_declaration_list")
    if not body:
        return
    for child in body.children:
        if child.type == "function_definition":
            sym = _extract_function(child, source, file_path, class_name)
            if sym:
                symbols.append(sym)
        elif child.type == "declaration":
            # Inline method declarations
            func_decl = _find_descendant(child, "function_declarator")
            if func_decl:
                name_node = _find_child(func_decl, "identifier") or _find_child(func_decl, "field_identifier")
                if name_node:
                    name = _node_text(name_node, source)
                    sig = _node_text(child, source).rstrip(";").strip()
                    sig = " ".join(sig.split())
                    symbols.append(CodeSymbol(
                        name=name,
                        qualified_name=f"{class_name}.{name}",
                        kind="method",
                        file_path=file_path,
                        start_line=child.start_point.row + 1,
                        end_line=child.end_point.row + 1,
                        signature=sig,
                        docstring=_extract_doc_comment(child, source),
                        parent_name=class_name,
                    ))
        elif child.type == "class_specifier":
            sym = _extract_class_or_struct(child, source, file_path, class_name, "class")
            if sym:
                symbols.append(sym)
        elif child.type == "struct_specifier":
            sym = _extract_class_or_struct(child, source, file_path, class_name, "struct")
            if sym:
                symbols.append(sym)


# ── Extractors ─────────────────────────────────────────────────


def _extract_function(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a function/method definition."""
    name = _find_function_name(node, source)
    if not name:
        return None

    # Detect qualified names like Config::method
    actual_parent = parent_name
    if "::" in name:
        parts = name.rsplit("::", 1)
        actual_parent = parts[0]
        name = parts[1]

    kind = "method" if actual_parent else "function"
    qualified = f"{actual_parent}.{name}" if actual_parent else name

    sig = _node_text(node, source).split("{")[0].strip()
    sig = " ".join(sig.split())

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=actual_parent,
    )


def _extract_class_or_struct(
    node: ts.Node, source: bytes, file_path: str,
    parent_name: str | None, kind: str,
) -> CodeSymbol | None:
    """Extract a class or struct specifier."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Build signature with base classes
    heritage = ""
    base_list = _find_child(node, "base_class_clause")
    if base_list:
        heritage = " " + _node_text(base_list, source)

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"{kind} {name}{heritage}",
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_enum(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract an enum (including enum class)."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Check for enum class
    is_scoped = any(c.type == "class" for c in node.children)
    prefix = "enum class" if is_scoped else "enum"

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="enum",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"{prefix} {name}",
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_namespace(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a namespace definition."""
    name_node = _find_child(node, "namespace_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="namespace",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"namespace {name}",
    )


def _extract_template(
    node: ts.Node, source: bytes, file_path: str,
    parent_name: str | None, symbols: list[CodeSymbol],
) -> None:
    """Extract the inner declaration from a template_declaration."""
    for child in node.children:
        if child.type == "function_definition":
            sym = _extract_function(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)
        elif child.type == "class_specifier":
            sym = _extract_class_or_struct(child, source, file_path, parent_name, "class")
            if sym:
                symbols.append(sym)
        elif child.type == "struct_specifier":
            sym = _extract_class_or_struct(child, source, file_path, parent_name, "struct")
            if sym:
                symbols.append(sym)
        elif child.type == "declaration":
            _extract_from_declaration(child, source, file_path, parent_name, symbols)


def _extract_from_declaration(
    node: ts.Node, source: bytes, file_path: str,
    parent_name: str | None, symbols: list[CodeSymbol],
) -> None:
    """Extract symbols from a declaration node (may contain class/struct/enum)."""
    for child in node.children:
        if child.type == "class_specifier":
            sym = _extract_class_or_struct(child, source, file_path, parent_name, "class")
            if sym:
                symbols.append(sym)
                _walk_class_body(child, source, file_path, sym.name, symbols)
        elif child.type == "struct_specifier":
            sym = _extract_class_or_struct(child, source, file_path, parent_name, "struct")
            if sym:
                symbols.append(sym)
                _walk_class_body(child, source, file_path, sym.name, symbols)
        elif child.type == "enum_specifier":
            sym = _extract_enum(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)


def _extract_include(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol:
    """Extract a #include directive."""
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


def _extract_typedef(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a typedef declaration."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = " ".join(_node_text(node, source).rstrip(";").strip().split())

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


# ── Helpers ────────────────────────────────────────────────────


def _find_function_name(node: ts.Node, source: bytes) -> str | None:
    """Find the function name from a function_definition."""
    for child in node.children:
        if child.type == "function_declarator":
            qid = _find_child(child, "qualified_identifier")
            if qid:
                return _node_text(qid, source)
            id_node = _find_child(child, "identifier") or _find_child(child, "field_identifier")
            if id_node:
                return _node_text(id_node, source)
        elif child.type == "pointer_declarator":
            result = _find_function_name_in_ptr(child, source)
            if result:
                return result
    return None


def _find_function_name_in_ptr(node: ts.Node, source: bytes) -> str | None:
    for child in node.children:
        if child.type == "function_declarator":
            qid = _find_child(child, "qualified_identifier")
            if qid:
                return _node_text(qid, source)
            id_node = _find_child(child, "identifier") or _find_child(child, "field_identifier")
            return _node_text(id_node, source) if id_node else None
        elif child.type == "pointer_declarator":
            return _find_function_name_in_ptr(child, source)
    return None


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract doc comment preceding a node."""
    if node.prev_sibling and node.prev_sibling.type == "comment":
        text = _node_text(node.prev_sibling, source).strip()
        if text.startswith("/**") and text.endswith("*/"):
            inner = text[3:-2].strip()
            lines = [l.strip().lstrip("* ").strip() for l in inner.split("\n")]
            return " ".join(l for l in lines if l and not l.startswith("@")) or None
        if text.startswith("//"):
            comments = [text[2:].strip()]
            sib = node.prev_sibling.prev_sibling
            while sib and sib.type == "comment":
                t = _node_text(sib, source).strip()
                if t.startswith("//"):
                    comments.append(t[2:].strip())
                else:
                    break
                sib = sib.prev_sibling
            comments.reverse()
            return " ".join(comments)
    return None


def _find_child(node: ts.Node, child_type: str) -> ts.Node | None:
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _find_descendant(node: ts.Node, target_type: str) -> ts.Node | None:
    for child in node.children:
        if child.type == target_type:
            return child
        result = _find_descendant(child, target_type)
        if result:
            return result
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
