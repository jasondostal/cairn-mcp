"""Shared orchestration for code intelligence operations.

Both MCP tools (server.py) and REST API (api/code.py) call these functions.
Keeps transport layers thin and prevents divergence.

NOTE: Code indexing is handled by the standalone code worker
(python -m cairn.code), not by the server. The server only queries.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_code_path(path: str, code_dir: str) -> Path | str:
    """Resolve and validate a code path against the configured code directory.

    Relative paths are resolved against code_dir. Absolute paths must be
    under code_dir (path traversal protection). Symlinks must not escape.

    Returns the resolved Path on success, or an error string on failure.
    """
    base = Path(code_dir).resolve()
    raw = Path(path)

    target = (base / raw if not raw.is_absolute() else raw).resolve()

    try:
        target.relative_to(base)
    except ValueError:
        return f"path must be under the code directory ({base}), got: {path}"

    if target.is_symlink():
        real = target.resolve()
        try:
            real.relative_to(base)
        except ValueError:
            return f"Symlink target is outside the code directory: {path}"

    if not target.is_dir():
        return f"Not a directory: {target}"

    return target


def run_code_query(
    *,
    action: str,
    project: str,
    target: str = "",
    query: str = "",
    kind: str = "",
    depth: int = 3,
    limit: int = 20,
    graph_provider: Any,
    db: Any,
    config: Any,
    embedding_engine: Any = None,
) -> dict:
    """Query the code graph for structural information."""
    if not action:
        return {"error": "action is required"}
    if not project:
        return {"error": "project is required"}

    if not config.capabilities.code_intelligence:
        return {"error": "Code intelligence is disabled. Set CAIRN_CODE_INTELLIGENCE=true."}

    from cairn.code.query import (
        query_call_chain,
        query_callees,
        query_callers,
        query_complexity,
        query_dead_code,
        query_dependencies,
        query_dependents,
        query_impact,
        query_search,
        query_structure,
    )
    from cairn.core.utils import get_or_create_project

    project_id = get_or_create_project(db, project)

    if action == "dependents":
        if not target:
            return {"error": "target is required for dependents"}
        return query_dependents(graph_provider, target, project_id)

    if action == "dependencies":
        if not target:
            return {"error": "target is required for dependencies"}
        return query_dependencies(graph_provider, target, project_id)

    if action == "structure":
        if not target:
            return {"error": "target is required for structure"}
        return query_structure(graph_provider, target, project_id)

    if action == "impact":
        if not target:
            return {"error": "target is required for impact"}
        return query_impact(graph_provider, target, project_id, max_depth=depth)

    if action == "search":
        if not query:
            return {"error": "query is required for search"}
        return query_search(
            graph_provider, query, project_id,
            kind=kind or None, limit=limit,
        )

    if action == "hotspots":
        from cairn.code.query import query_hotspots
        return query_hotspots(graph_provider, project_id, limit=limit)

    if action == "callers":
        if not target:
            return {"error": "target (qualified name) is required for callers"}
        return query_callers(graph_provider, target, project_id, limit=limit)

    if action == "callees":
        if not target:
            return {"error": "target (qualified name) is required for callees"}
        return query_callees(graph_provider, target, project_id, limit=limit)

    if action == "call_chain":
        if not target or not query:
            return {"error": "target (start symbol) and query (end symbol) are required for call_chain"}
        return query_call_chain(
            graph_provider, target, query, project_id,
            max_depth=depth, limit=limit,
        )

    if action == "dead_code":
        return query_dead_code(graph_provider, project_id, limit=limit)

    if action == "complexity":
        return query_complexity(graph_provider, project_id, limit=limit)

    if action == "entities":
        if not target:
            return {"error": "target is required for entities"}
        entities = graph_provider.get_entities_for_code(target, project_id)
        return {"target": target, "entities": entities}

    if action == "code_for_entity":
        if not target:
            return {"error": "target (entity name) is required for code_for_entity"}
        known = graph_provider.get_known_entities(project_id, limit=500)
        entity_uuid = None
        for e in known:
            if e["name"].lower() == target.lower():
                if embedding_engine:
                    emb = embedding_engine.embed(target)
                    matches = graph_provider.search_entities_by_embedding(emb, project_id, limit=1)
                    if matches:
                        entity_uuid = matches[0].uuid
                break
        if not entity_uuid:
            return {"target": target, "code": [], "error": f"Entity not found: {target}"}
        code = graph_provider.get_code_for_entity(entity_uuid)
        return {"target": target, "code": code}

    if action == "cross_search":
        if not query:
            return {"error": "query is required for cross_search"}
        from cairn.code.query import query_cross_search
        all_project_ids = _get_all_code_project_ids(db)
        return query_cross_search(graph_provider, query, all_project_ids, kind=kind or None, limit=limit)

    if action == "shared_deps":
        from cairn.code.query import query_shared_dependencies
        all_project_ids = _get_all_code_project_ids(db)
        return query_shared_dependencies(graph_provider, all_project_ids)

    if action == "bridge":
        from cairn.code.bridge import CodeBridgeService
        bridge_svc = CodeBridgeService(graph_provider)
        return bridge_svc.bridge_all(project_id)

    return {
        "error": f"Unknown action: {action}. Valid: dependents, dependencies, structure, "
        "impact, search, hotspots, callers, callees, call_chain, dead_code, complexity, "
        "entities, code_for_entity, cross_search, shared_deps, bridge"
    }


def run_arch_check(
    *,
    project: str,
    path: str = "",
    config_path: str = "",
    use_graph: bool = False,
    graph_provider: Any,
    db: Any,
    config: Any,
    project_manager: Any,
) -> dict:
    """Check architecture boundary rules and integration contracts."""
    if not project:
        return {"error": "project is required"}

    if not config.capabilities.code_intelligence:
        return {"error": "Code intelligence is disabled. Set CAIRN_CODE_INTELLIGENCE=true."}

    from cairn.code.arch_rules import (
        check as arch_check_source,
    )
    from cairn.code.arch_rules import (
        check_graph as arch_check_graph,
    )
    from cairn.code.arch_rules import (
        load_config as load_arch_config,
    )
    from cairn.code.arch_rules import (
        load_config_from_string,
    )
    from cairn.core.utils import get_or_create_project

    # 1. Load rules
    arch_config = None
    if config_path:
        cp = Path(config_path)
        if not cp.is_file():
            return {"error": f"Config file not found: {config_path}"}
        arch_config = load_arch_config(cp)
    else:
        docs = project_manager.get_docs(project, doc_type="architecture")
        if docs:
            arch_config = load_config_from_string(docs[0]["content"])
        else:
            return {"error": "No architecture rules found. Provide config_path or store rules as a project doc (doc_type='architecture')."}

    project_id = get_or_create_project(db, project)

    # 2. Evaluate
    if use_graph:
        report = arch_check_graph(arch_config, graph_provider, project_id)
        evaluation_mode = "graph"
    else:
        if not path:
            return {"error": "path is required for source-based evaluation (or set use_graph=True)"}
        resolved = _resolve_code_path(path, config.code_dir)
        if isinstance(resolved, str):
            return {"error": resolved}
        report = arch_check_source(arch_config, resolved)
        evaluation_mode = "source"

    # 3. Build response
    violations = [
        {
            "rule_name": v.rule_name,
            "file_path": str(v.file_path),
            "imported_module": v.imported_module,
            "lineno": v.lineno,
            "description": v.description,
        }
        for v in report.violations
    ]

    contract_violations = [
        {
            "rule_module": cv.rule_module,
            "consumer_file": cv.consumer_file,
            "imported_name": cv.imported_name,
            "lineno": cv.lineno,
        }
        for cv in report.contract_violations
    ]

    return {
        "project": project,
        "clean": report.clean,
        "violations": violations,
        "contract_violations": contract_violations,
        "files_checked": report.files_checked,
        "rules_evaluated": report.rules_evaluated,
        "evaluation_mode": evaluation_mode,
        "summary": report.summary(),
    }


def _get_all_code_project_ids(db: Any) -> list[int]:
    """Get all project IDs from the projects table."""
    try:
        rows = db.execute("SELECT id FROM projects", ())
        return [r["id"] for r in rows] if rows else []
    except Exception:
        return []
