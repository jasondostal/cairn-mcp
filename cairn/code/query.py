"""Structural queries over the code graph.

Thin orchestration layer between MCP tools and GraphProvider.
Each function validates input, dispatches to graph methods, and
formats results for MCP consumption.

Target resolution: ``target`` can be a file path or a qualified symbol
name.  File-level queries (dependents, dependencies, impact) resolve
symbols to their containing file.  Structure queries on a symbol
return its children.
"""

from __future__ import annotations

import logging
from typing import Any

from cairn.graph.interface import GraphProvider

logger = logging.getLogger(__name__)


def _resolve_file_path(
    graph: GraphProvider,
    target: str,
    project_id: int,
) -> str | None:
    """Resolve *target* to a file path.

    If *target* already looks like a file path (contains ``/`` or ``.py``)
    and exists in the graph, return it directly.  Otherwise treat it as a
    qualified symbol name and look up the symbol's ``file_path``.
    """
    # Fast path: target looks like a file path
    if "/" in target or any(target.endswith(ext) for ext in (".py", ".ts", ".tsx")):
        cf = graph.get_code_file(target, project_id)
        if cf:
            return target
        # Try suffix match — target may be relative while graph stores absolute paths
        all_files = graph.get_code_files(project_id)
        suffix = target.lstrip("/")
        for f in all_files:
            if f["path"].endswith("/" + suffix) or f["path"] == suffix:
                return f["path"]
        return None

    # Slow path: treat as qualified symbol name — search for it
    results = graph.search_code_symbols(target, project_id, limit=1)
    if results:
        return results[0].get("file_path")
    return None


def query_dependents(
    graph: GraphProvider,
    target: str,
    project_id: int,
) -> dict[str, Any]:
    """Files that IMPORT the target file."""
    file_path = _resolve_file_path(graph, target, project_id)
    if not file_path:
        return {"target": target, "files": [], "error": f"Target not found: {target}"}

    files = graph.get_file_dependents(file_path, project_id)
    return {"target": file_path, "files": files}


def query_dependencies(
    graph: GraphProvider,
    target: str,
    project_id: int,
) -> dict[str, Any]:
    """Files that the target file IMPORTS."""
    file_path = _resolve_file_path(graph, target, project_id)
    if not file_path:
        return {"target": target, "files": [], "error": f"Target not found: {target}"}

    files = graph.get_file_dependencies(file_path, project_id)
    return {"target": file_path, "files": files}


def query_structure(
    graph: GraphProvider,
    target: str,
    project_id: int,
) -> dict[str, Any]:
    """Symbols in the target file, organized hierarchically."""
    file_path = _resolve_file_path(graph, target, project_id)
    if not file_path:
        return {"target": target, "symbols": [], "error": f"Target not found: {target}"}

    flat = graph.get_file_structure(file_path, project_id)

    # Build hierarchical view: top-level symbols with children nested
    top_level: list[dict] = []
    by_name: dict[str, dict] = {}

    for sym in flat:
        entry = {
            "name": sym["name"],
            "qualified_name": sym["qualified_name"],
            "kind": sym["kind"],
            "start_line": sym["start_line"],
            "end_line": sym["end_line"],
            "signature": sym.get("signature", ""),
            "docstring": sym.get("docstring"),
        }
        by_name[sym["qualified_name"]] = entry

        if sym.get("parent_name") and sym["parent_name"] in by_name:
            parent = by_name[sym["parent_name"]]
            parent.setdefault("children", []).append(entry)
        else:
            top_level.append(entry)

    return {"target": file_path, "symbols": top_level}


def query_impact(
    graph: GraphProvider,
    target: str,
    project_id: int,
    max_depth: int = 3,
) -> dict[str, Any]:
    """Transitive blast radius: files affected if this file changes."""
    file_path = _resolve_file_path(graph, target, project_id)
    if not file_path:
        return {
            "target": target,
            "depth": max_depth,
            "affected_files": 0,
            "layers": [],
            "error": f"Target not found: {target}",
        }

    rows = graph.get_impact_graph(file_path, project_id, max_depth=max_depth)

    # Group by depth
    layers: dict[int, list[dict]] = {}
    for row in rows:
        d = row["depth"]
        layers.setdefault(d, []).append({"path": row["path"], "language": row["language"]})

    sorted_layers = [
        {"depth": d, "files": layers[d]}
        for d in sorted(layers)
    ]

    return {
        "target": file_path,
        "depth": max_depth,
        "affected_files": len(rows),
        "layers": sorted_layers,
    }


def query_callers(
    graph: GraphProvider,
    target: str,
    project_id: int,
    limit: int = 50,
) -> dict[str, Any]:
    """Functions/methods that CALL the target symbol."""
    results = graph.get_callers(target, project_id, limit=limit)
    return {"target": target, "callers": results}


def query_callees(
    graph: GraphProvider,
    target: str,
    project_id: int,
    limit: int = 50,
) -> dict[str, Any]:
    """Functions/methods that the target symbol CALLS."""
    results = graph.get_callees(target, project_id, limit=limit)
    return {"target": target, "callees": results}


def query_call_chain(
    graph: GraphProvider,
    start: str,
    end: str,
    project_id: int,
    max_depth: int = 5,
    limit: int = 20,
) -> dict[str, Any]:
    """Find call chains from start to end symbol."""
    results = graph.get_call_chain(start, end, project_id, max_depth=max_depth, limit=limit)
    return {"start": start, "end": end, "chains": results}


def query_dead_code(
    graph: GraphProvider,
    project_id: int,
    limit: int = 50,
) -> dict[str, Any]:
    """Find functions/methods with zero incoming CALLS edges."""
    results = graph.get_dead_code(project_id, limit=limit)
    return {"dead_functions": results, "count": len(results)}


def query_complexity(
    graph: GraphProvider,
    project_id: int,
    limit: int = 20,
) -> dict[str, Any]:
    """Get symbols ranked by cyclomatic complexity."""
    results = graph.get_most_complex(project_id, limit=limit)
    return {"most_complex": results}


def query_search(
    graph: GraphProvider,
    query: str,
    project_id: int,
    kind: str | None = None,
    limit: int = 20,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Fulltext search over code symbols (name, qualified_name, signature, docstring)."""
    results = graph.search_code_symbols(
        query=query,
        project_id=project_id,
        kind=kind or None,
        limit=limit,
    )
    return {"query": query, "mode": "fulltext", "results": results}


# -- Phase 7: Cross-project analysis --


def query_hotspots(
    graph: GraphProvider,
    project_id: int,
    limit: int = 20,
) -> dict[str, Any]:
    """Compute PageRank over IMPORTS graph, return top files by structural importance."""
    import networkx as nx

    files = graph.get_code_files(project_id)
    G = nx.DiGraph()
    for f in files:
        G.add_node(f["path"])

    # Add IMPORTS edges
    for f in files:
        deps = graph.get_file_dependencies(f["path"], project_id)
        for d in deps:
            G.add_edge(f["path"], d["path"])

    if not G.nodes:
        return {"project_id": project_id, "hotspots": []}

    pr = nx.pagerank(G)
    ranked = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:limit]
    return {
        "project_id": project_id,
        "hotspots": [{"path": p, "pagerank": round(score, 6)} for p, score in ranked],
    }


def query_cross_search(
    graph: GraphProvider,
    query: str,
    project_ids: list[int],
    kind: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search code symbols across multiple projects."""
    results = graph.search_code_symbols_cross_project(
        query=query,
        project_ids=project_ids,
        kind=kind or None,
        limit=limit,
    )
    return {"query": query, "project_ids": project_ids, "results": results}


def query_shared_dependencies(
    graph: GraphProvider,
    project_ids: list[int],
) -> dict[str, Any]:
    """Find modules/files imported by multiple projects."""
    results = graph.get_shared_dependencies(project_ids)
    return {"project_ids": project_ids, "shared": results}
