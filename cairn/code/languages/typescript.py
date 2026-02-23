"""TypeScript/TSX language support for tree-sitter parsing.

Extracts functions, classes, methods, interfaces, type aliases, enums,
arrow functions, React components, React hooks, and imports from
TypeScript and TSX source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_typescript as tstypescript

from cairn.code.parser import CodeSymbol

_LANGUAGES: dict[str, ts.Language] = {}


def get_language(dialect: str = "typescript") -> ts.Language:
    """Return the TypeScript or TSX tree-sitter Language (cached).

    Args:
        dialect: "typescript" or "tsx".
    """
    if dialect not in _LANGUAGES:
        if dialect == "tsx":
            _LANGUAGES[dialect] = ts.Language(tstypescript.language_tsx())
        else:
            _LANGUAGES[dialect] = ts.Language(tstypescript.language_typescript())
    return _LANGUAGES[dialect]


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed TypeScript/TSX AST.

    Walks the tree and extracts:
      - Functions (including arrow functions assigned to const)
      - Classes (with their methods as children)
      - Interfaces
      - Type aliases
      - Enums
      - React components (functions returning JSX)
      - React hooks (functions starting with 'use')
      - Imports
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
        if child.type == "function_declaration":
            sym = _extract_function(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "class_declaration":
            sym = _extract_class(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)
                body = _find_child(child, "class_body")
                if body:
                    _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)

        elif child.type == "method_definition":
            sym = _extract_method(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "interface_declaration":
            sym = _extract_interface(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "type_alias_declaration":
            sym = _extract_type_alias(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "enum_declaration":
            sym = _extract_enum(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "lexical_declaration" and parent_name is None:
            # const foo = () => {} or const Foo = () => <div/>
            sym = _extract_arrow_function(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "export_statement":
            # Unwrap export to get the actual definition
            _walk_export(child, source, file_path, parent_name, symbols)

        elif child.type == "import_statement" and parent_name is None:
            sym = _extract_import(child, source, file_path)
            if sym:
                symbols.append(sym)


def _walk_export(
    node: ts.Node,
    source: bytes,
    file_path: str,
    parent_name: str | None,
    symbols: list[CodeSymbol],
) -> None:
    """Unwrap an export_statement and extract the inner definition."""
    for child in node.children:
        if child.type in (
            "function_declaration", "class_declaration",
            "interface_declaration", "type_alias_declaration",
            "enum_declaration", "lexical_declaration",
        ):
            # Recurse into the inner definition as if it were top-level
            inner_symbols: list[CodeSymbol] = []
            _walk_node_single(child, source, file_path, parent_name, inner_symbols)
            # Adjust start_line to include the export keyword
            export_start = node.start_point.row + 1
            for sym in inner_symbols:
                if sym.start_line > export_start:
                    sym = CodeSymbol(
                        name=sym.name,
                        qualified_name=sym.qualified_name,
                        kind=sym.kind,
                        file_path=sym.file_path,
                        start_line=export_start,
                        end_line=sym.end_line,
                        signature=sym.signature,
                        docstring=sym.docstring,
                        parent_name=sym.parent_name,
                    )
                symbols.append(sym)


def _walk_node_single(
    child: ts.Node,
    source: bytes,
    file_path: str,
    parent_name: str | None,
    symbols: list[CodeSymbol],
) -> None:
    """Process a single node (not its children list)."""
    if child.type == "function_declaration":
        sym = _extract_function(child, source, file_path, parent_name)
        if sym:
            symbols.append(sym)

    elif child.type == "class_declaration":
        sym = _extract_class(child, source, file_path, parent_name)
        if sym:
            symbols.append(sym)
            body = _find_child(child, "class_body")
            if body:
                _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)

    elif child.type == "interface_declaration":
        sym = _extract_interface(child, source, file_path)
        if sym:
            symbols.append(sym)

    elif child.type == "type_alias_declaration":
        sym = _extract_type_alias(child, source, file_path)
        if sym:
            symbols.append(sym)

    elif child.type == "enum_declaration":
        sym = _extract_enum(child, source, file_path)
        if sym:
            symbols.append(sym)

    elif child.type == "lexical_declaration" and parent_name is None:
        sym = _extract_arrow_function(child, source, file_path)
        if sym:
            symbols.append(sym)


def _extract_function(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a function declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    params_node = _find_child(node, "formal_parameters")
    params = _node_text(params_node, source) if params_node else "()"

    # Return type
    return_type = ""
    ret_node = _find_child(node, "type_annotation")
    if ret_node:
        return_type = _node_text(ret_node, source)

    # Determine kind: component, hook, method, or function
    kind = _classify_function(name, node, source, parent_name)
    qualified = f"{parent_name}.{name}" if parent_name else name

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"function {name}{params}{return_type}",
        docstring=_extract_jsdoc(node, source),
        parent_name=parent_name,
    )


def _extract_class(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a class declaration."""
    name_node = _find_child(node, "identifier") or _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)

    # Heritage (extends/implements)
    heritage = ""
    for child in node.children:
        if child.type in ("class_heritage", "extends_clause", "implements_clause"):
            heritage = " " + _node_text(child, source)
            break

    qualified = f"{parent_name}.{name}" if parent_name else name

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="class",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"class {name}{heritage}",
        docstring=_extract_jsdoc(node, source),
        parent_name=parent_name,
    )


def _extract_method(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a method definition from a class body."""
    name_node = _find_child(node, "property_identifier")
    if not name_node:
        name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    params_node = _find_child(node, "formal_parameters")
    params = _node_text(params_node, source) if params_node else "()"

    return_type = ""
    ret_node = _find_child(node, "type_annotation")
    if ret_node:
        return_type = _node_text(ret_node, source)

    qualified = f"{parent_name}.{name}" if parent_name else name

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="method",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"{name}{params}{return_type}",
        docstring=_extract_jsdoc(node, source),
        parent_name=parent_name,
    )


def _extract_interface(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an interface declaration."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)

    # Type parameters
    type_params = ""
    tp = _find_child(node, "type_parameters")
    if tp:
        type_params = _node_text(tp, source)

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="interface",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"interface {name}{type_params}",
        docstring=_extract_jsdoc(node, source),
    )


def _extract_type_alias(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a type alias declaration."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)

    # Get the first line of the type as signature
    text = _node_text(node, source)
    sig = text.split("\n")[0].rstrip()

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="type_alias",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
    )


def _extract_enum(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an enum declaration."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="enum",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"enum {name}",
    )


def _extract_arrow_function(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an arrow function assigned to a const/let variable.

    Matches patterns like:
      const foo = () => { ... }
      const Foo = (props) => <div/>
    """
    # lexical_declaration -> variable_declarator -> arrow_function
    for decl in node.children:
        if decl.type != "variable_declarator":
            continue

        name_node = _find_child(decl, "identifier")
        if not name_node:
            continue

        # Check if the value is an arrow_function
        arrow = _find_child(decl, "arrow_function")
        if not arrow:
            continue

        name = _node_text(name_node, source)
        params_node = _find_child(arrow, "formal_parameters")
        params = _node_text(params_node, source) if params_node else "()"

        return_type = ""
        ret_node = _find_child(arrow, "type_annotation")
        if ret_node:
            return_type = _node_text(ret_node, source)

        kind = _classify_function(name, arrow, source, parent_name=None)

        return CodeSymbol(
            name=name,
            qualified_name=name,
            kind=kind,
            file_path=file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            signature=f"const {name} = {params}{return_type} => ...",
            docstring=_extract_jsdoc(node, source),
        )
    return None


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


# ── Classification helpers ────────────────────────────────────


def _classify_function(
    name: str, node: ts.Node, source: bytes, parent_name: str | None,
) -> str:
    """Classify a function as component, hook, method, or function."""
    if parent_name:
        return "method"

    # React hooks: functions starting with 'use'
    if name.startswith("use") and len(name) > 3 and name[3].isupper():
        return "hook"

    # React components: PascalCase name and contains JSX in body
    if name and name[0].isupper() and _contains_jsx(node):
        return "component"

    return "function"


def _contains_jsx(node: ts.Node) -> bool:
    """Check if a function body contains JSX elements."""
    body = _find_child(node, "statement_block")
    if not body:
        # Arrow function with expression body (no braces)
        for child in node.children:
            if child.type in ("jsx_element", "jsx_self_closing_element", "jsx_fragment", "parenthesized_expression"):
                if child.type == "parenthesized_expression":
                    return _has_jsx_descendant(child)
                return True
        return False
    return _has_jsx_descendant(body)


def _has_jsx_descendant(node: ts.Node) -> bool:
    """Recursively check if any descendant is a JSX element."""
    for child in node.children:
        if child.type in ("jsx_element", "jsx_self_closing_element", "jsx_fragment"):
            return True
        if _has_jsx_descendant(child):
            return True
    return False


# ── General helpers ────────────────────────────────────────────


def _find_child(node: ts.Node, child_type: str) -> ts.Node | None:
    """Find the first direct child of a given type."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    """Get the text of a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _extract_jsdoc(node: ts.Node, source: bytes) -> str | None:
    """Extract JSDoc comment preceding a node.

    Looks for a comment sibling immediately before the node.
    """
    if node.prev_sibling and node.prev_sibling.type == "comment":
        text = _node_text(node.prev_sibling, source).strip()
        # Parse JSDoc: /** ... */
        if text.startswith("/**") and text.endswith("*/"):
            # Strip comment delimiters and leading asterisks
            lines = text[3:-2].strip().split("\n")
            cleaned = []
            for line in lines:
                line = line.strip()
                if line.startswith("* "):
                    line = line[2:]
                elif line.startswith("*"):
                    line = line[1:]
                # Skip @param, @returns etc. for now — just get description
                if not line.startswith("@"):
                    cleaned.append(line.strip())
            doc = " ".join(cleaned).strip()
            return doc if doc else None
    return None
