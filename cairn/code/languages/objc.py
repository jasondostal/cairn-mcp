"""Objective-C language support for tree-sitter parsing.

Extracts classes (interfaces/implementations), protocols, methods,
properties, and imports from Objective-C source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_objc as tsobjc

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Objective-C tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsobjc.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Objective-C AST.

    Walks the tree and extracts:
      - Class interfaces and implementations
      - Protocols
      - Methods (instance and class)
      - Properties
      - #import directives
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
    """Walk declarations in an Objective-C source file."""
    for child in node.children:
        if child.type == "preproc_include":
            sym = _extract_import(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "class_interface":
            _extract_class_interface(child, source, file_path, symbols)

        elif child.type == "class_implementation":
            _extract_class_implementation(child, source, file_path, symbols)

        elif child.type == "protocol_declaration":
            _extract_protocol(child, source, file_path, symbols)

        elif child.type == "method_declaration":
            sym = _extract_method_decl(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "property_declaration":
            sym = _extract_property(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "implementation_definition":
            # Contains method_definition inside @implementation
            method_def = _find_child(child, "method_definition")
            if method_def:
                sym = _extract_method_def(method_def, source, file_path, parent_name)
                if sym:
                    symbols.append(sym)

        elif child.type == "function_definition":
            sym = _extract_function(child, source, file_path)
            if sym:
                symbols.append(sym)


# -- Extractors ---------------------------------------------------------------


def _extract_import(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a #import directive."""
    # preproc_include > #import, system_lib_string or string_literal
    lib_node = _find_child(node, "system_lib_string")
    if not lib_node:
        str_node = _find_child(node, "string_literal")
        if str_node:
            content = _find_child(str_node, "string_content")
            name = _node_text(content, source) if content else _node_text(str_node, source).strip("\"")
        else:
            return None
    else:
        name = _node_text(lib_node, source)

    sig = _node_text(node, source).strip()
    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
    )


def _extract_class_interface(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract a @interface class declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    sig = _node_text(node, source).split("\n")[0].strip()

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=name,
        kind="class",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
    ))

    # Walk children for methods and properties
    _walk_node(node, source, file_path, symbols, parent_name=name)


def _extract_class_implementation(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract a @implementation class."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)

    # Walk children for method definitions
    _walk_node(node, source, file_path, symbols, parent_name=name)


def _extract_protocol(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract a @protocol declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=name,
        kind="protocol",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"@protocol {name}",
    ))

    # Walk children for method declarations
    _walk_node(node, source, file_path, symbols, parent_name=name)


def _extract_method_decl(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a method declaration (- or + prefixed)."""
    return _extract_method_common(node, source, file_path, parent_name)


def _extract_method_def(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a method definition."""
    return _extract_method_common(node, source, file_path, parent_name)


def _extract_method_common(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Common method extraction for both declarations and definitions."""
    # Method prefix: - (instance) or + (class)
    full_text = _node_text(node, source).strip()
    is_class_method = full_text.startswith("+")

    # Find the method selector (identifier children)
    name_node = _find_child(node, "identifier")
    if not name_node:
        # Try keyword_selector for multi-part selectors
        selector = _find_child(node, "keyword_selector")
        if selector:
            parts = []
            for child in selector.children:
                if child.type == "keyword_declarator":
                    kw = _find_child(child, "identifier")
                    if kw:
                        parts.append(_node_text(kw, source) + ":")
            name = "".join(parts) if parts else None
        else:
            return None
    else:
        name = _node_text(name_node, source)

    if not name:
        return None

    prefix = "+" if is_class_method else "-"
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = full_text.split("{")[0].strip().rstrip(";").strip()

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="method",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        parent_name=parent_name,
    )


def _extract_property(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a @property declaration."""
    # The property name is usually the last identifier in struct_declaration
    struct_decl = _find_child(node, "struct_declaration")
    if not struct_decl:
        return None

    # Find the declarator which contains the property name
    # Structure: struct_declaration > struct_declarator > pointer_declarator
    name = None
    for child in struct_decl.children:
        if child.type == "struct_declarator":
            # Inside struct_declarator, look for pointer_declarator or identifier
            for inner in child.children:
                if inner.type in ("pointer_declarator", "identifier"):
                    text = _node_text(inner, source).strip().lstrip("*")
                    if text:
                        name = text
                        break
        elif child.type in ("pointer_declarator", "identifier"):
            text = _node_text(child, source).strip().lstrip("*")
            if text:
                name = text

    if not name:
        return None

    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).strip()

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="property",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        parent_name=parent_name,
    )


def _extract_function(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a C-style function definition."""
    # function_definition > type, declarator, body
    declarator = _find_child(node, "function_declarator")
    if not declarator:
        return None

    name_node = _find_child(declarator, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = _node_text(node, source).split("{")[0].strip()

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="function",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
    )


# -- Helpers -------------------------------------------------------------------


def _find_child(node: ts.Node, child_type: str) -> ts.Node | None:
    """Find the first direct child of a given type."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    """Get the text of a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
