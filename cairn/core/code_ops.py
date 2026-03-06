"""Shared orchestration for code intelligence operations.

Both MCP tools (server.py) and REST API (api/code.py) call these functions.
Keeps transport layers thin and prevents divergence.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def run_code_index(
    *,
    project: str,
    path: str,
    force: bool = False,
    graph_provider: Any,
    db: Any,
    config: Any,
) -> dict:
    """Index a codebase for structural analysis.

    Returns a result dict with files_scanned, files_indexed, etc.
    """
    if not project:
        return {"error": "project is required"}
    if not path:
        return {"error": "path is required"}

    root = Path(path)
    if not root.is_dir():
        return {"error": f"Not a directory: {path}"}

    if not graph_provider:
        return {"error": "Code intelligence requires Neo4j. Set CAIRN_GRAPH_BACKEND=neo4j."}

    if not config.capabilities.code_intelligence:
        return {"error": "Code intelligence is disabled. Set CAIRN_CODE_INTELLIGENCE=true."}

    from cairn.code.indexer import CodeIndexer
    from cairn.code.parser import CodeParser
    from cairn.core.utils import get_or_create_project

    project_id = get_or_create_project(db, project)
    parser = CodeParser()
    indexer = CodeIndexer(parser, graph_provider)

    result = indexer.index_directory(
        root=root,
        project=project,
        project_id=project_id,
        force=force,
    )

    # Bridge entities to code (best-effort)
    bridge_stats = None
    if result.files_indexed > 0:
        try:
            from cairn.code.bridge import CodeBridgeService
            pid = get_or_create_project(db, project)
            bridge_svc = CodeBridgeService(graph_provider)
            bridge_stats = bridge_svc.bridge_all(pid)
        except Exception:
            logger.warning("Code bridge after index failed (non-blocking)", exc_info=True)

    resp = {
        "project": result.project,
        "files_scanned": result.files_scanned,
        "files_indexed": result.files_indexed,
        "files_skipped": result.files_skipped,
        "files_deleted": result.files_deleted,
        "symbols_created": result.symbols_created,
        "imports_created": result.imports_created,
        "errors": result.errors if result.errors else None,
        "summary": result.summary(),
    }
    if bridge_stats:
        resp["bridge"] = bridge_stats
    return resp


def run_code_query(
    *,
    action: str,
    project: str,
    target: str = "",
    query: str = "",
    kind: str = "",
    depth: int = 3,
    limit: int = 20,
    mode: str = "fulltext",
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

    if not graph_provider:
        return {"error": "Code queries require Neo4j. Set CAIRN_GRAPH_BACKEND=neo4j."}

    if not config.capabilities.code_intelligence:
        return {"error": "Code intelligence is disabled. Set CAIRN_CODE_INTELLIGENCE=true."}

    from cairn.code.query import (
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
            kind=kind or None, limit=limit, mode=mode,
            embedding_engine=embedding_engine if mode == "semantic" else None,
        )

    if action == "hotspots":
        from cairn.code.query import query_hotspots
        return query_hotspots(graph_provider, project_id, limit=limit)

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
        "impact, search, hotspots, entities, code_for_entity, cross_search, shared_deps, bridge"
    }


def run_code_describe(
    *,
    project: str,
    target: str = "",
    kind: str = "",
    limit: int = 50,
    graph_provider: Any,
    db: Any,
    config: Any,
    llm: Any,
    embedding_engine: Any,
) -> dict:
    """Generate natural language descriptions for code symbols."""
    if not project:
        return {"error": "project is required"}

    if not graph_provider:
        return {"error": "Code describe requires Neo4j. Set CAIRN_GRAPH_BACKEND=neo4j."}

    if not config.capabilities.code_intelligence:
        return {"error": "Code intelligence is disabled. Set CAIRN_CODE_INTELLIGENCE=true."}

    if not llm:
        return {"error": "Code describe requires LLM. Enable enrichment."}

    from cairn.code.summarizer import CodeSummarizer
    from cairn.core.utils import get_or_create_project

    project_id = get_or_create_project(db, project)
    summarizer = CodeSummarizer(llm, embedding_engine)

    # Gather symbols
    if target:
        symbols = graph_provider.get_code_symbols(target, project_id)
    else:
        files = graph_provider.get_code_files(project_id)
        symbols = []
        for f in files:
            file_syms = graph_provider.get_code_symbols(f["path"], project_id)
            symbols.extend(file_syms)

    # Filter
    filtered = symbols
    if kind:
        filtered = [s for s in filtered if s.get("kind") == kind]
    filtered = [s for s in filtered if not s.get("description")]
    filtered = filtered[:limit]

    if not filtered:
        return {"project": project, "described": 0, "message": "No undescribed symbols found"}

    described = summarizer.batch_describe(filtered, project_id)

    stored = 0
    for item in described:
        try:
            graph_provider.update_code_symbol_description(
                qualified_name=item["qualified_name"],
                project_id=project_id,
                file_path=item["file_path"],
                description=item["description"],
                description_embedding=item["embedding"],
            )
            stored += 1
        except Exception:
            logger.warning("Failed to store description for %s", item["qualified_name"], exc_info=True)

    return {
        "project": project,
        "described": stored,
        "symbols": [
            {"qualified_name": d["qualified_name"], "description": d["description"]}
            for d in described[:10]
        ],
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

    if not graph_provider:
        return {"error": "Architecture checks require Neo4j. Set CAIRN_GRAPH_BACKEND=neo4j."}

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
        root = Path(path)
        if not root.is_dir():
            return {"error": f"Not a directory: {path}"}
        report = arch_check_source(arch_config, root)
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
