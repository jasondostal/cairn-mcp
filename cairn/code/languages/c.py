"""C language support for tree-sitter parsing.

Extracts functions, structs, enums, typedefs, macros/defines,
and #include directives from C source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_c as tsc

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the C tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsc.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed C AST."""
    symbols: list[CodeSymbol] = []
    _walk_node(tree.root_node, source, file_path, symbols)
    return symbols


def _walk_node(
    node: ts.Node, source: bytes, file_path: str, symbols: list[CodeSymbol],
) -> None:
    """Walk top-level declarations in a C source file."""
    for child in node.children:
        if child.type == "function_definition":
            sym = _extract_function(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "declaration":
            sym = _extract_declaration(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "type_definition":
            sym = _extract_typedef(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "struct_specifier":
            sym = _extract_struct_or_enum(child, source, file_path, "struct")
            if sym:
                symbols.append(sym)

        elif child.type == "enum_specifier":
            sym = _extract_struct_or_enum(child, source, file_path, "enum")
            if sym:
                symbols.append(sym)

        elif child.type == "preproc_include":
            sym = _extract_include(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "preproc_def":
            sym = _extract_define(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "preproc_function_def":
            sym = _extract_define(child, source, file_path)
            if sym:
                symbols.append(sym)


# ── Extractors ─────────────────────────────────────────────────


def _extract_function(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a function definition.

    C function names are nested inside declarators:
      function_definition -> function_declarator -> identifier
      function_definition -> pointer_declarator -> function_declarator -> identifier
    """
    name = _find_function_name(node, source)
    if not name:
        return None

    sig = _node_text(node, source).split("{")[0].strip()
    # Collapse multi-line signatures
    sig = " ".join(sig.split())

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


def _extract_declaration(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a forward declaration (function prototype)."""
    # Only extract function prototypes, not variable declarations
    func_decl = _find_descendant(node, "function_declarator")
    if not func_decl:
        return None

    name_node = _find_child(func_decl, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = _node_text(node, source).rstrip(";").strip()
    sig = " ".join(sig.split())

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


def _extract_typedef(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a typedef declaration."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)

    # Determine if it's a struct/enum typedef
    kind = "type_alias"
    for child in node.children:
        if child.type == "struct_specifier":
            kind = "struct"
        elif child.type == "enum_specifier":
            kind = "enum"

    sig = " ".join(_node_text(node, source).rstrip(";").strip().split())

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


def _extract_struct_or_enum(
    node: ts.Node, source: bytes, file_path: str, kind: str,
) -> CodeSymbol | None:
    """Extract a named struct or enum specifier (not inside typedef)."""
    name_node = _find_child(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = f"{kind} {name}"

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


def _extract_define(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a #define macro."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = _node_text(node, source).split("\n")[0].strip()

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="constant",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
    )


# ── Helpers ────────────────────────────────────────────────────


def _find_function_name(node: ts.Node, source: bytes) -> str | None:
    """Find the function name from a function_definition.

    Handles direct declarators and pointer declarators.
    """
    for child in node.children:
        if child.type == "function_declarator":
            id_node = _find_child(child, "identifier")
            return _node_text(id_node, source) if id_node else None
        elif child.type == "pointer_declarator":
            return _find_function_name_in_declarator(child, source)
    return None


def _find_function_name_in_declarator(node: ts.Node, source: bytes) -> str | None:
    """Recursively find function name inside pointer/parenthesized declarators."""
    for child in node.children:
        if child.type == "function_declarator":
            id_node = _find_child(child, "identifier")
            return _node_text(id_node, source) if id_node else None
        elif child.type in ("pointer_declarator", "parenthesized_declarator"):
            return _find_function_name_in_declarator(child, source)
    return None


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract doc comment (/** ... */ or consecutive //) preceding a node."""
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
    """Find first descendant of a given type (BFS)."""
    for child in node.children:
        if child.type == target_type:
            return child
        result = _find_descendant(child, target_type)
        if result:
            return result
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
