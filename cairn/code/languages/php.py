"""PHP language support for tree-sitter parsing.

Extracts classes, interfaces, traits, enums, functions, methods,
constants, and use/namespace declarations from PHP source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_php as tsphp

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the PHP tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsphp.language_php())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed PHP AST."""
    symbols: list[CodeSymbol] = []
    # PHP wraps everything in a program node
    root = tree.root_node
    if root.type == "program":
        _walk_node(root, source, file_path, parent_name=None, symbols=symbols)
    else:
        _walk_node(root, source, file_path, parent_name=None, symbols=symbols)
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
                body = _find_child(child, "declaration_list")
                if body:
                    _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)

        elif child.type == "interface_declaration":
            sym = _extract_interface(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)
                body = _find_child(child, "declaration_list")
                if body:
                    _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)

        elif child.type == "trait_declaration":
            sym = _extract_trait(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)
                body = _find_child(child, "declaration_list")
                if body:
                    _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)

        elif child.type == "enum_declaration":
            sym = _extract_enum(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "function_definition":
            sym = _extract_function(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "method_declaration":
            sym = _extract_method(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "const_declaration":
            _extract_const(child, source, file_path, parent_name, symbols)

        elif child.type == "namespace_use_declaration":
            sym = _extract_use(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "namespace_definition":
            # Walk into namespace body
            body = _find_child(child, "compound_statement")
            if body:
                _walk_node(body, source, file_path, parent_name, symbols)


# ── Extractors ─────────────────────────────────────────────────


def _extract_class(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a class declaration."""
    name_node = _find_child(node, "name")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Heritage
    heritage = ""
    base = _find_child(node, "base_clause")
    if base:
        heritage += " " + _node_text(base, source)
    ifaces = _find_child(node, "class_interface_clause")
    if ifaces:
        heritage += " " + _node_text(ifaces, source)

    mods = _extract_modifiers(node, source)

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="class",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"{mods}class {name}{heritage}".strip(),
        docstring=_extract_phpdoc(node, source),
        parent_name=parent_name,
    )


def _extract_interface(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract an interface declaration."""
    name_node = _find_child(node, "name")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="interface",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"interface {name}",
        docstring=_extract_phpdoc(node, source),
        parent_name=parent_name,
    )


def _extract_trait(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a trait declaration."""
    name_node = _find_child(node, "name")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="trait",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"trait {name}",
        docstring=_extract_phpdoc(node, source),
        parent_name=parent_name,
    )


def _extract_enum(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract an enum declaration (PHP 8.1+)."""
    name_node = _find_child(node, "name")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="enum",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"enum {name}",
        docstring=_extract_phpdoc(node, source),
        parent_name=parent_name,
    )


def _extract_function(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a function definition."""
    name_node = _find_child(node, "name")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    params = _find_child(node, "formal_parameters")
    params_text = _node_text(params, source) if params else "()"

    return_type = ""
    for child in node.children:
        if child.type in ("union_type", "named_type", "primitive_type",
                          "optional_type", "nullable_type", "intersection_type"):
            return_type = f": {_node_text(child, source)}"
            break

    kind = "method" if parent_name else "function"

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"function {name}{params_text}{return_type}",
        docstring=_extract_phpdoc(node, source),
        parent_name=parent_name,
    )


def _extract_method(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a method declaration."""
    name_node = _find_child(node, "name")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    mods = _extract_modifiers(node, source)
    params = _find_child(node, "formal_parameters")
    params_text = _node_text(params, source) if params else "()"

    return_type = ""
    for child in node.children:
        if child.type in ("union_type", "named_type", "primitive_type",
                          "optional_type", "nullable_type", "intersection_type"):
            return_type = f": {_node_text(child, source)}"
            break

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="method",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"{mods}function {name}{params_text}{return_type}".strip(),
        docstring=_extract_phpdoc(node, source),
        parent_name=parent_name,
    )


def _extract_const(
    node: ts.Node, source: bytes, file_path: str,
    parent_name: str | None, symbols: list[CodeSymbol],
) -> None:
    """Extract const declarations (single and grouped)."""
    for child in node.children:
        if child.type == "const_element":
            name_node = _find_child(child, "name")
            if not name_node:
                continue
            name = _node_text(name_node, source)
            sig = _node_text(child, source).split("\n")[0].strip()
            symbols.append(CodeSymbol(
                name=name,
                qualified_name=f"{parent_name}.{name}" if parent_name else name,
                kind="constant",
                file_path=file_path,
                start_line=child.start_point.row + 1,
                end_line=child.end_point.row + 1,
                signature=f"const {sig}",
                docstring=_extract_phpdoc(node, source),
                parent_name=parent_name,
            ))


def _extract_use(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol:
    """Extract a namespace use declaration."""
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
    """Extract visibility/modifier keywords."""
    parts = []
    for child in node.children:
        if child.type in ("visibility_modifier", "static_modifier",
                          "abstract_modifier", "final_modifier", "readonly_modifier"):
            parts.append(_node_text(child, source))
    return " ".join(parts) + " " if parts else ""


def _extract_phpdoc(node: ts.Node, source: bytes) -> str | None:
    """Extract PHPDoc comment preceding a declaration."""
    if node.prev_sibling and node.prev_sibling.type == "comment":
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
                if not line.startswith("@"):
                    lines.append(line)
            doc = " ".join(l for l in lines if l).strip()
            return doc if doc else None
    return None


def _find_child(node: ts.Node, child_type: str) -> ts.Node | None:
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
