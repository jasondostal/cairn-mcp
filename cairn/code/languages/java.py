"""Java language support for tree-sitter parsing.

Extracts classes, interfaces, enums, records, methods, constructors,
fields, and imports from Java source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_java as tsjava

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Java tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsjava.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Java AST."""
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
        if child.type == "class_declaration":
            sym = _extract_class(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)
                body = _find_child(child, "class_body")
                if body:
                    _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)

        elif child.type == "interface_declaration":
            sym = _extract_interface(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)
                body = _find_child(child, "interface_body")
                if body:
                    _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)

        elif child.type == "enum_declaration":
            sym = _extract_enum(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "record_declaration":
            sym = _extract_record(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "method_declaration":
            sym = _extract_method(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "constructor_declaration":
            sym = _extract_constructor(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "field_declaration" and parent_name:
            sym = _extract_field(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "import_declaration":
            sym = _extract_import(child, source, file_path)
            if sym:
                symbols.append(sym)


# ── Extractors ─────────────────────────────────────────────────


def _extract_class(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a class declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Build signature with modifiers and heritage
    mods = _extract_modifiers(node, source)
    type_params = _find_child(node, "type_parameters")
    tp = _node_text(type_params, source) if type_params else ""

    heritage = ""
    for child in node.children:
        if child.type == "superclass":
            heritage += f" {_node_text(child, source)}"
        elif child.type == "super_interfaces":
            heritage += f" {_node_text(child, source)}"

    sig = f"{mods}class {name}{tp}{heritage}".strip()

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="class",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_javadoc(node, source),
        parent_name=parent_name,
    )


def _extract_interface(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract an interface declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    mods = _extract_modifiers(node, source)
    type_params = _find_child(node, "type_parameters")
    tp = _node_text(type_params, source) if type_params else ""

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="interface",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"{mods}interface {name}{tp}".strip(),
        docstring=_extract_javadoc(node, source),
        parent_name=parent_name,
    )


def _extract_enum(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract an enum declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    mods = _extract_modifiers(node, source)

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="enum",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"{mods}enum {name}".strip(),
        docstring=_extract_javadoc(node, source),
        parent_name=parent_name,
    )


def _extract_record(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a record declaration (Java 16+)."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    mods = _extract_modifiers(node, source)
    params = _find_child(node, "formal_parameters")
    params_text = _node_text(params, source) if params else "()"

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="record",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"{mods}record {name}{params_text}".strip(),
        docstring=_extract_javadoc(node, source),
        parent_name=parent_name,
    )


def _extract_method(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a method declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    mods = _extract_modifiers(node, source)

    # Return type — comes before the identifier
    return_type = ""
    for child in node.children:
        if child == name_node:
            break
        if child.type in (
            "type_identifier", "generic_type", "void_type",
            "integral_type", "floating_point_type", "boolean_type",
            "array_type", "scoped_type_identifier",
        ):
            return_type = _node_text(child, source)

    params = _find_child(node, "formal_parameters")
    params_text = _node_text(params, source) if params else "()"

    sig = f"{mods}{return_type} {name}{params_text}".strip()

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="method",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_javadoc(node, source),
        parent_name=parent_name,
    )


def _extract_constructor(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a constructor declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    mods = _extract_modifiers(node, source)
    params = _find_child(node, "formal_parameters")
    params_text = _node_text(params, source) if params else "()"

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="constructor",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"{mods}{name}{params_text}".strip(),
        docstring=_extract_javadoc(node, source),
        parent_name=parent_name,
    )


def _extract_field(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a static final field (constant) from a class body."""
    text = _node_text(node, source)
    # Only extract static final fields as constants
    if "static" not in text or "final" not in text:
        return None

    # Find the variable declarator for the name
    declarator = _find_child(node, "variable_declarator")
    if not declarator:
        return None
    name_node = _find_child(declarator, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = text.split("\n")[0].rstrip().rstrip(";").rstrip()

    return CodeSymbol(
        name=name,
        qualified_name=f"{parent_name}.{name}" if parent_name else name,
        kind="constant",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        parent_name=parent_name,
    )


def _extract_import(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol:
    """Extract an import declaration."""
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


# ── Helpers ────────────────────────────────────────────────────


def _extract_modifiers(node: ts.Node, source: bytes) -> str:
    """Extract visibility/modifier keywords (public, static, abstract, etc.)."""
    mods_node = _find_child(node, "modifiers")
    if mods_node:
        return _node_text(mods_node, source) + " "
    return ""


def _extract_javadoc(node: ts.Node, source: bytes) -> str | None:
    """Extract Javadoc comment preceding a declaration.

    Looks at prev_sibling for a block_comment starting with /**.
    """
    if node.prev_sibling and node.prev_sibling.type == "block_comment":
        text = _node_text(node.prev_sibling, source).strip()
        if text.startswith("/**") and text.endswith("*/"):
            inner = text[3:-2].strip()
            lines = []
            for line in inner.split("\n"):
                line = line.strip()
                if line.startswith("* "):
                    line = line[2:]
                elif line.startswith("*"):
                    line = line[1:]
                line = line.strip()
                # Skip @param, @return, @throws tags
                if not line.startswith("@"):
                    lines.append(line)
            doc = " ".join(l for l in lines if l).strip()
            return doc if doc else None
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
