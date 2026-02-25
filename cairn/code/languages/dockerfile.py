"""Dockerfile language support for tree-sitter parsing.

Extracts FROM stages (with aliases), ENV, EXPOSE, LABEL, and ARG
directives from Dockerfile source files.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_dockerfile as tsdocker

from cairn.code.parser import CodeSymbol

_LANGUAGE: ts.Language | None = None


def get_language() -> ts.Language:
    """Return the Dockerfile tree-sitter Language (cached)."""
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = ts.Language(tsdocker.language())
    return _LANGUAGE


def extract_symbols(tree: ts.Tree, source: bytes, file_path: str) -> list[CodeSymbol]:
    """Extract code symbols from a parsed Dockerfile AST.

    Walks the tree and extracts:
      - FROM stages (with AS aliases)
      - ENV directives
      - EXPOSE directives
      - LABEL directives
      - ARG directives
    """
    symbols: list[CodeSymbol] = []
    _walk_node(tree.root_node, source, file_path, symbols)
    return symbols


def _walk_node(
    node: ts.Node,
    source: bytes,
    file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Walk top-level instructions in a Dockerfile."""
    for child in node.children:
        if child.type == "from_instruction":
            sym = _extract_from(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "env_instruction":
            _extract_env(child, source, file_path, symbols)

        elif child.type == "expose_instruction":
            sym = _extract_expose(child, source, file_path)
            if sym:
                symbols.append(sym)

        elif child.type == "label_instruction":
            _extract_label(child, source, file_path, symbols)

        elif child.type == "arg_instruction":
            sym = _extract_arg(child, source, file_path)
            if sym:
                symbols.append(sym)


# -- Extractors -----------------------------------------------------


def _extract_from(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract a FROM instruction.

    Structure: from_instruction > FROM image_spec [AS image_alias]
    """
    image_spec = _find_child(node, "image_spec")
    if not image_spec:
        return None

    image_name = _find_child(image_spec, "image_name")
    image_tag = _find_child(image_spec, "image_tag")

    name_text = _node_text(image_name, source) if image_name else "unknown"
    if image_tag:
        name_text += _node_text(image_tag, source)

    alias_node = _find_child(node, "image_alias")
    alias = _node_text(alias_node, source) if alias_node else None

    if alias:
        name = alias
        sig = f"FROM {name_text} AS {alias}"
    else:
        name = name_text
        sig = f"FROM {name_text}"

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="stage",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
    )


def _extract_env(
    node: ts.Node, source: bytes, file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract ENV key=value pairs.

    Structure: env_instruction > ENV env_pair+
    Each env_pair has unquoted_string = unquoted_string.
    """
    for child in node.children:
        if child.type == "env_pair":
            # First child of env_pair is the key (unquoted_string)
            key_node = _find_child(child, "unquoted_string")
            if not key_node:
                continue
            key = _node_text(key_node, source)
            sig = _node_text(node, source).split("\n")[0].rstrip()

            symbols.append(CodeSymbol(
                name=key,
                qualified_name=key,
                kind="env",
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                signature=sig,
                docstring=_extract_doc_comment(node, source),
            ))


def _extract_expose(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an EXPOSE instruction.

    Structure: expose_instruction > EXPOSE expose_port
    """
    port_node = _find_child(node, "expose_port")
    if not port_node:
        return None

    port = _node_text(port_node, source)
    sig = f"EXPOSE {port}"

    return CodeSymbol(
        name=port,
        qualified_name=port,
        kind="expose",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
    )


def _extract_label(
    node: ts.Node, source: bytes, file_path: str,
    symbols: list[CodeSymbol],
) -> None:
    """Extract LABEL key=value pairs.

    Structure: label_instruction > LABEL label_pair+
    """
    for child in node.children:
        if child.type == "label_pair":
            key_node = _find_child(child, "unquoted_string")
            if not key_node:
                continue
            key = _node_text(key_node, source)
            sig = _node_text(node, source).split("\n")[0].rstrip()

            symbols.append(CodeSymbol(
                name=key,
                qualified_name=key,
                kind="label",
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                signature=sig,
            ))


def _extract_arg(
    node: ts.Node, source: bytes, file_path: str,
) -> CodeSymbol | None:
    """Extract an ARG instruction.

    Structure: arg_instruction > ARG unquoted_string [= unquoted_string]
    """
    name_node = _find_child(node, "unquoted_string")
    if not name_node:
        return None

    name = _node_text(name_node, source)
    sig = _node_text(node, source).split("\n")[0].rstrip()

    return CodeSymbol(
        name=name,
        qualified_name=name,
        kind="arg",
        file_path=file_path,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        signature=sig,
        docstring=_extract_doc_comment(node, source),
    )


# -- Helpers --------------------------------------------------------


def _extract_doc_comment(node: ts.Node, source: bytes) -> str | None:
    """Extract Dockerfile doc comment preceding an instruction.

    Dockerfiles use # for comments.
    """
    comments: list[str] = []
    sibling = node.prev_sibling

    # Skip whitespace/newline nodes
    while sibling and sibling.type == "\n":
        sibling = sibling.prev_sibling

    while sibling and sibling.type == "comment":
        text = _node_text(sibling, source).strip()
        if text.startswith("#"):
            line = text[1:].strip()
            if line:
                comments.append(line)
        sibling = sibling.prev_sibling

    if comments:
        comments.reverse()
        return " ".join(comments)
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
