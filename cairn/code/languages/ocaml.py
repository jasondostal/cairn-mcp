"""OCaml language support for tree-sitter parsing.

Extracts let bindings, type definitions, module definitions,
and open statements from OCaml source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_ocaml as tsocaml

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the OCaml tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsocaml.language_ocaml())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed OCaml AST.

    Walks the tree and extracts:
      - Let bindings (value_definition) as function/variable
      - Type definitions (type_definition) as type
      - Module definitions (module_definition) as module
      - Open statements (open_module) as import
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
    """Walk declarations in an OCaml source file."""
    for child in node.children:
        if child.type == "value_definition":
            syms = _extract_value_def(child, source, file_path, parent_name)
            symbols.extend(syms)

        elif child.type == "type_definition":
            syms = _extract_type_def(child, source, file_path, parent_name)
            symbols.extend(syms)

        elif child.type == "module_definition":
            _extract_module(child, source, file_path, symbols, parent_name)

        elif child.type == "open_module":
            sym = _extract_open(child, source, file_path)
            if sym:
                symbols.append(sym)


# -- Extractors ---------------------------------------------------------------


def _extract_value_def(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> list[CodeSymbol]:
    """Extract let/let rec bindings."""
    symbols: list[CodeSymbol] = []
    is_rec = any(c.type == "rec" for c in node.children)

    for child in node.children:
        if child.type == "let_binding":
            sym = _extract_let_binding(child, source, file_path, parent_name, is_rec)
            if sym:
                symbols.append(sym)

    return symbols


def _extract_let_binding(
    node: ts.Node,
    source: bytes,
    file_path: str,
    parent_name: str | None,
    is_rec: bool,
) -> CodeSymbol | None:
    """Extract a single let binding."""
    name_node = _find_child(node, "value_name")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Determine if it's a function (has parameters) or a value
    has_params = any(c.type == "parameter" for c in node.children)
    kind = "function" if has_params else "variable"
    if parent_name and has_params:
        kind = "method"

    # Build signature
    sig_parts = ["let"]
    if is_rec:
        sig_parts.append("rec")
    sig_parts.append(name)

    # Add parameters
    for child in node.children:
        if child.type == "parameter":
            sig_parts.append(_node_text(child, source))

    sig = " ".join(sig_parts)
    if len(sig) > 120:
        sig = sig[:117] + "..."

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node.parent, source) if node.parent else None,
        parent_name=parent_name,
    )


def _extract_type_def(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> list[CodeSymbol]:
    """Extract type definitions."""
    symbols: list[CodeSymbol] = []

    for child in node.children:
        if child.type == "type_binding":
            name_node = _find_child(child, "type_constructor")
            if not name_node:
                continue

            name = _node_text(name_node, source)
            qualified = f"{parent_name}.{name}" if parent_name else name
            sig = _node_text(node, source).split("\n")[0].strip()

            symbols.append(CodeSymbol(
                name=name,
                qualified_name=qualified,
                kind="type",
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                signature=sig,
                docstring=_extract_doc_comment(node, source),
                parent_name=parent_name,
            ))

    return symbols


def _extract_module(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
    parent_name: str | None,
) -> None:
    """Extract a module definition."""
    binding = _find_child(node, "module_binding")
    if not binding:
        return

    name_node = _find_child(binding, "module_name")
    if not name_node:
        return

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    sig = f"module {name}"

    symbols.append(CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="module",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    ))

    # Walk module body for members
    structure = _find_child(binding, "structure")
    if structure:
        _walk_node(structure, source, file_path, symbols, parent_name=name)


def _extract_open(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an open statement (module import)."""
    mod_path = _find_child(node, "module_path")
    if not mod_path:
        return None

    mod_name_node = _find_child(mod_path, "module_name")
    name = _node_text(mod_name_node, source) if mod_name_node else _node_text(mod_path, source)

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="import",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"open {name}",
    )


# -- Helpers -------------------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract OCaml doc comment preceding a declaration.

    OCaml uses (** ... *) for documentation comments.
    """
    sibling = node.prev_sibling

    if sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("(**") and text.endswith("*)"):
            inner = text[3:-2].strip()
            return inner or None

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
