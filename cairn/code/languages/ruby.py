"""Ruby language support for tree-sitter parsing.

Extracts classes, modules, methods, singleton methods, constants,
and require statements from Ruby source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_ruby as tsruby

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Ruby tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsruby.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Ruby AST."""
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
        if child.type == "class":
            sym = _extract_class(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)
                body = _find_child(child, "body_statement")
                if body:
                    _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)

        elif child.type == "module":
            sym = _extract_module(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)
                body = _find_child(child, "body_statement")
                if body:
                    _walk_node(body, source, file_path, parent_name=sym.name, symbols=symbols)

        elif child.type == "method":
            sym = _extract_method(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "singleton_method":
            sym = _extract_singleton_method(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "assignment":
            sym = _extract_constant(child, source, file_path, parent_name)
            if sym:
                symbols.append(sym)

        elif child.type == "call":
            sym = _extract_require(child, source, file_path)
            if sym:
                symbols.append(sym)


# ── Extractors ─────────────────────────────────────────────────


def _extract_class(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a class definition."""
    name_node = _find_child(node, "constant")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    # Superclass
    superclass = _find_child(node, "superclass")
    heritage = ""
    if superclass:
        heritage = f" < {_node_text(superclass, source).lstrip('< ').strip()}"

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="class",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"class {name}{heritage}",
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_module(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a module definition."""
    name_node = _find_child(node, "constant")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="module",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"module {name}",
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_method(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a method definition."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name
    kind = "method" if parent_name else "function"

    params = _find_child(node, "method_parameters")
    params_text = _node_text(params, source) if params else ""

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"def {name}{params_text}",
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_singleton_method(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a singleton/class method (def self.method)."""
    name_node = _find_child(node, "identifier")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    qualified = f"{parent_name}.{name}" if parent_name else name

    params = _find_child(node, "method_parameters")
    params_text = _node_text(params, source) if params else ""

    return CodeSymbol(
        name=name,
        qualified_name=qualified,
        kind="method",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=f"def self.{name}{params_text}",
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_constant(
    node: ts.Node, source: bytes, file_path: str, parent_name: str | None,
) -> CodeSymbol | None:
    """Extract a constant assignment (UPPER_CASE = value)."""
    # First child should be a constant node (capitalized)
    if not node.children:
        return None
    left = node.children[0]
    if left.type != "constant":
        return None

    name = _node_text(left, source)
    sig = _node_text(node, source).split("\n")[0].strip()

    return CodeSymbol(
        name=name,
        qualified_name=f"{parent_name}.{name}" if parent_name else name,
        kind="constant",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
        parent_name=parent_name,
    )


def _extract_require(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract require/require_relative calls as imports."""
    method_node = _find_child(node, "identifier")
    if not method_node:
        return None

    method_name = _node_text(method_node, source)
    if method_name not in ("require", "require_relative"):
        return None

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


# ── Helpers ────────────────────────────────────────────────────


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Ruby doc comment (consecutive # lines) preceding a node."""
    comments: list[str] = []
    sibling = node.prev_sibling

    while sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("#"):
            line = text[1:].strip()
            comments.append(line)
        else:
            break
        sibling = sibling.prev_sibling

    if comments:
        comments.reverse()
        return " ".join(comments)
    return None


def _find_child(node: ts.Node, child_type: str) -> ts.Node | None:
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _node_text(node: ts.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
