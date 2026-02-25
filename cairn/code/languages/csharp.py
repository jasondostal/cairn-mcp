"""C# language support for tree-sitter parsing.

Extracts namespaces, classes, interfaces, enums, methods,
properties, fields, and imports (using directives) from C# source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_c_sharp as tscsharp

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the C# tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tscsharp.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed C# AST.

    Walks the tree and extracts:
      - Namespaces (namespace_declaration)
      - Classes (class_declaration)
      - Interfaces (interface_declaration)
      - Enums (enum_declaration)
      - Methods (method_declaration)
      - Properties (property_declaration)
      - Fields (field_declaration)
      - Using directives (using_directive)
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
    """Walk declarations in a C# source file."""
    for child in node.children:
        if child.type == "using_directive":
            sym = _extract_using(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "namespace_declaration":
            _extract_namespace(child, source, file_path, symbols, parent_name)

        elif child.type == "class_declaration":
            _extract_class(child, source, file_path, symbols, parent_name)

        elif child.type == "interface_declaration":
            _extract_interface(child, source, file_path, symbols, parent_name)

        elif child.type == "enum_declaration":
            _extract_enum(child, source, file_path, symbols, parent_name)

        elif child.type == "method_declaration":
            sym = _extract_method(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "property_declaration":
            sym = _extract_property(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "field_declaration":
            sym = _extract_field(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)


# -- Extractors --------------------------------------------------------


def _extract_using(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a using directive."""
    # using_directive has children: using, identifier or qualified_name, ;
    name_node = _find_child(node, "qualified_name") or _find_child(node, "identifier")
    if not name_node:
        return None

    text = _node_text(name_node, source).strip()
    return CodeSymbol(
        name=text,
        qualified_name=text,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"using {text}",
    )


def _extract_namespace(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract a namespace declaration."""
    name_node = _find_child(node, "identifier") or _find_child(node, "qualified_name")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = f"namespace {name}"

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="namespace",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    ))

    # Walk declaration_list for members
    decl_list = _find_child(node, "declaration_list")
    if decl_list:
        _walk_node(decl_list, source, file_path, symbols, parent_name=name)


def _extract_class(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract a class declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    sig = _node_text(node, source).split("{")[0].strip()

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="class",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    ))

    # Walk declaration_list for members
    decl_list = _find_child(node, "declaration_list")
    if decl_list:
        _walk_node(decl_list, source, file_path, symbols, parent_name=name)


def _extract_interface(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract an interface declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("{")[0].strip()

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="interface",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    ))

    # Walk declaration_list for members
    decl_list = _find_child(node, "declaration_list")
    if decl_list:
        _walk_node(decl_list, source, file_path, symbols, parent_name=name)


def _extract_enum(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract an enum declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
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


def _extract_method(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a method declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    kind = "method"
    qualified = f"{parent_name}.{name}" if parent_name else name

    sig = _node_text(node, source).split("{")[0].strip()
    # Remove trailing ; for interface methods
    sig = sig.rstrip(";").strip()

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


def _extract_property(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a property declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("\n")[0].strip()

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="property",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_field(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a field declaration."""
    # field_declaration has children: modifier, variable_declaration, ;
    var_decl = _find_child(node, "variable_declaration")
    if not var_decl:
        return None

    # variable_declaration has children: type, variable_declarator(s)
    declarator = _find_child(var_decl, "variable_declarator")
    if not declarator:
        return None

    name_node = _find_child(declarator, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = _node_text(node, source).split("\n")[0].strip().rstrip(";").strip()

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="field",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


# -- Helpers -----------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract C# XML doc comment preceding a declaration.

    C# uses /// XML doc comments. The summary text is extracted
    from consecutive /// comment lines.
    """
    comments: list[str] = []
    sibling = node.prev_sibling

    while sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("///"):
            line = text[3:].strip()
            # Strip XML tags like <summary>, </summary>
            line = _strip_xml_tags(line)
            if line:
                comments.append(line)
        sibling = sibling.prev_sibling

    if comments:
        comments.reverse()
        return " ".join(comments)

    return None


def _strip_xml_tags(text: str) -> str:
    """Strip XML tags from a doc comment line."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


def _find_child(node: ts.Node, child_type: str) -> ts.Node | None:
    """Find the first direct child of a given type."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    """Get the text of a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
