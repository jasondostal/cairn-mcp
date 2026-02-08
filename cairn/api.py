"""Cairn REST API — read-only endpoints for the web UI."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, APIRouter, Query, Path, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from cairn.core.services import Services
from cairn.core.status import get_status

logger = logging.getLogger(__name__)


def create_api(svc: Services) -> FastAPI:
    """Build the read-only REST API as a FastAPI app.

    Designed to be mounted as a sub-app on the MCP Starlette parent.
    No lifespan needed — the parent handles DB lifecycle.
    """
    db = svc.db
    config = svc.config
    memory_store = svc.memory_store
    search_engine = svc.search_engine
    cluster_engine = svc.cluster_engine
    project_manager = svc.project_manager
    task_manager = svc.task_manager
    thinking_engine = svc.thinking_engine
    cairn_manager = svc.cairn_manager
    app = FastAPI(
        title="Cairn API",
        version="0.9.0",
        description="Read-only REST API for the Cairn web UI.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    router = APIRouter()

    # ------------------------------------------------------------------
    # GET /status — system health
    # ------------------------------------------------------------------
    @router.get("/status")
    def api_status():
        return get_status(db, config)

    # ------------------------------------------------------------------
    # GET /timeline?project=&type=&days=&limit=&offset=
    # ------------------------------------------------------------------
    @router.get("/timeline")
    def api_timeline(
        project: str | None = Query(None),
        type: str | None = Query(None),
        days: int = Query(7, ge=1, le=365),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        where = ["m.is_active = true", "m.created_at >= %s"]
        params: list = [cutoff]

        if project:
            where.append("p.name = %s")
            params.append(project)
        if type:
            where.append("m.memory_type = %s")
            params.append(type)

        where_clause = " AND ".join(where)

        count_row = db.execute_one(
            f"""
            SELECT COUNT(*) as total FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where_clause}
            """,
            tuple(params),
        )
        total = count_row["total"]

        query_params = list(params)
        query_params.extend([limit, offset])

        rows = db.execute(
            f"""
            SELECT m.id, m.summary, m.content, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.related_files, m.is_active,
                   m.session_name, m.created_at, m.updated_at,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where_clause}
            ORDER BY m.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(query_params),
        )

        items = [
            {
                "id": r["id"],
                "summary": r["summary"],
                "content": r["content"],
                "memory_type": r["memory_type"],
                "importance": r["importance"],
                "project": r["project"],
                "tags": r["tags"],
                "auto_tags": r["auto_tags"],
                "related_files": r["related_files"],
                "is_active": r["is_active"],
                "session_name": r["session_name"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]

        return {"total": total, "limit": limit, "offset": offset, "items": items}

    # ------------------------------------------------------------------
    # GET /search?q=&project=&type=&mode=&limit=&offset=
    # ------------------------------------------------------------------
    @router.get("/search")
    def api_search(
        q: str = Query(..., description="Search query"),
        project: str | None = Query(None),
        type: str | None = Query(None),
        mode: str = Query("semantic"),
        limit: int = Query(10, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        results = search_engine.search(
            query=q,
            project=project,
            memory_type=type,
            search_mode=mode,
            limit=limit + offset,
            include_full=True,
        )
        # Search engine doesn't support native offset, so slice
        items = results[offset:offset + limit]
        return {"total": len(results), "limit": limit, "offset": offset, "items": items}

    # ------------------------------------------------------------------
    # GET /memories/:id — single memory with full content
    # ------------------------------------------------------------------
    @router.get("/memories/{memory_id}")
    def api_memory(memory_id: int = Path(...)):
        results = memory_store.recall([memory_id])
        if not results:
            raise HTTPException(status_code=404, detail="Memory not found")
        return results[0]

    # ------------------------------------------------------------------
    # GET /projects?limit=&offset=
    # ------------------------------------------------------------------
    @router.get("/projects")
    def api_projects(
        limit: int | None = Query(None, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return project_manager.list_all(limit=limit, offset=offset)

    # ------------------------------------------------------------------
    # GET /projects/:name — project docs + links
    # ------------------------------------------------------------------
    @router.get("/projects/{name}")
    def api_project_detail(name: str = Path(...)):
        docs = project_manager.get_docs(name)
        links = project_manager.get_links(name)
        return {"name": name, "docs": docs, "links": links}

    # ------------------------------------------------------------------
    # GET /clusters/visualization?project=
    # ------------------------------------------------------------------
    @router.get("/clusters/visualization")
    def api_cluster_visualization(
        project: str | None = Query(None),
    ):
        return cluster_engine.get_visualization(project=project)

    # ------------------------------------------------------------------
    # GET /clusters?project=&topic=&min_confidence=&limit=
    # ------------------------------------------------------------------
    @router.get("/clusters")
    def api_clusters(
        project: str | None = Query(None),
        topic: str | None = Query(None),
        min_confidence: float = Query(0.5, ge=0.0, le=1.0),
        limit: int = Query(10, ge=1, le=100),
    ):
        if cluster_engine.is_stale(project):
            cluster_engine.run_clustering(project)

        clusters = cluster_engine.get_clusters(
            project=project,
            topic=topic,
            min_confidence=min_confidence,
            limit=limit,
        )
        return {"cluster_count": len(clusters), "clusters": clusters}

    # ------------------------------------------------------------------
    # GET /tasks?project=&include_completed=&limit=&offset=
    # ------------------------------------------------------------------
    @router.get("/tasks")
    def api_tasks(
        project: str | None = Query(None),
        include_completed: bool = Query(False),
        limit: int | None = Query(None, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return task_manager.list_tasks(
            project=project, include_completed=include_completed,
            limit=limit, offset=offset,
        )

    # ------------------------------------------------------------------
    # GET /thinking?project=&status=&limit=&offset=
    # ------------------------------------------------------------------
    @router.get("/thinking")
    def api_thinking_list(
        project: str | None = Query(None),
        status: str | None = Query(None),
        limit: int | None = Query(None, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return thinking_engine.list_sequences(
            project=project, status=status, limit=limit, offset=offset,
        )

    # ------------------------------------------------------------------
    # GET /thinking/:id — sequence with all thoughts
    # ------------------------------------------------------------------
    @router.get("/thinking/{sequence_id}")
    def api_thinking_detail(sequence_id: int = Path(...)):
        try:
            return thinking_engine.get_sequence(sequence_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Thinking sequence not found")

    # ------------------------------------------------------------------
    # GET /cairns?project=&limit=
    # ------------------------------------------------------------------
    @router.get("/cairns")
    def api_cairns(
        project: str | None = Query(None, description="Project name (omit for all projects)"),
        limit: int = Query(20, ge=1, le=50),
    ):
        return cairn_manager.stack(project=project, limit=limit)

    # ------------------------------------------------------------------
    # POST /cairns — set a cairn (used by hooks)
    # ------------------------------------------------------------------
    @router.post("/cairns")
    def api_set_cairn(body: dict):
        project = body.get("project")
        session_name = body.get("session_name")
        events = body.get("events")

        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        if not session_name:
            raise HTTPException(status_code=400, detail="session_name is required")

        result = cairn_manager.set(project, session_name, events=events)
        if "error" in result:
            raise HTTPException(status_code=409, detail=result["error"])
        return result

    # ------------------------------------------------------------------
    # GET /cairns/:id — single cairn with full detail + linked stones
    # ------------------------------------------------------------------
    @router.get("/cairns/{cairn_id}")
    def api_cairn_detail(cairn_id: int = Path(...)):
        try:
            return cairn_manager.get(cairn_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Cairn not found")

    # ------------------------------------------------------------------
    # GET /rules?project=&limit=&offset=
    # ------------------------------------------------------------------
    @router.get("/rules")
    def api_rules(
        project: str | None = Query(None),
        limit: int | None = Query(None, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return memory_store.get_rules(project, limit=limit, offset=offset)

    # ------------------------------------------------------------------
    # GET /graph?project=&relation_type=&min_importance=
    # ------------------------------------------------------------------
    @router.get("/graph")
    def api_graph(
        project: str | None = Query(None),
        relation_type: str | None = Query(None),
        min_importance: float = Query(0.0, ge=0.0, le=1.0),
    ):
        NODE_CAP = 500

        # Build edge query with filters
        edge_where = ["m1.is_active = true", "m2.is_active = true"]
        edge_params: list = []

        if project:
            edge_where.append("(p1.name = %s OR p2.name = %s)")
            edge_params.extend([project, project])
        if relation_type:
            edge_where.append("mr.relation = %s")
            edge_params.append(relation_type)
        if min_importance > 0:
            edge_where.append("(m1.importance >= %s OR m2.importance >= %s)")
            edge_params.extend([min_importance, min_importance])

        edge_clause = " AND ".join(edge_where)

        edges_raw = db.execute(
            f"""
            SELECT mr.source_id, mr.target_id, mr.relation, mr.created_at
            FROM memory_relations mr
            JOIN memories m1 ON mr.source_id = m1.id
            JOIN memories m2 ON mr.target_id = m2.id
            LEFT JOIN projects p1 ON m1.project_id = p1.id
            LEFT JOIN projects p2 ON m2.project_id = p2.id
            WHERE {edge_clause}
            ORDER BY mr.created_at DESC
            LIMIT 2000
            """,
            tuple(edge_params),
        )

        # Collect unique node IDs
        node_ids: set[int] = set()
        edges = []
        for row in edges_raw:
            node_ids.add(row["source_id"])
            node_ids.add(row["target_id"])
            edges.append({
                "source": row["source_id"],
                "target": row["target_id"],
                "relation": row["relation"] or "related",
                "created_at": row["created_at"].isoformat(),
            })

        if not node_ids:
            return {
                "nodes": [],
                "edges": [],
                "stats": {"node_count": 0, "edge_count": 0, "relation_types": {}},
            }

        # Cap nodes by importance if too many
        id_list = list(node_ids)
        if len(id_list) > NODE_CAP:
            placeholders = ",".join(["%s"] * len(id_list))
            top_nodes = db.execute(
                f"""
                SELECT id FROM memories
                WHERE id IN ({placeholders})
                ORDER BY importance DESC
                LIMIT %s
                """,
                tuple(id_list) + (NODE_CAP,),
            )
            id_list = [r["id"] for r in top_nodes]
            node_ids = set(id_list)
            edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

        # Fetch node details
        placeholders = ",".join(["%s"] * len(id_list))
        nodes_raw = db.execute(
            f"""
            SELECT m.id, m.summary, m.memory_type, m.importance, m.created_at,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE m.id IN ({placeholders})
            """,
            tuple(id_list),
        )

        nodes = [
            {
                "id": r["id"],
                "summary": r["summary"] or f"Memory #{r['id']}",
                "memory_type": r["memory_type"],
                "importance": float(r["importance"]),
                "project": r["project"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in nodes_raw
        ]

        # Stats
        relation_counts: dict[str, int] = {}
        for e in edges:
            rel = e["relation"]
            relation_counts[rel] = relation_counts.get(rel, 0) + 1

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "relation_types": relation_counts,
            },
        }

    # ------------------------------------------------------------------
    # GET /export?project=&format=
    # ------------------------------------------------------------------
    @router.get("/export")
    def api_export(
        project: str = Query(..., description="Project name (required)"),
        format: str = Query("json", description="Export format: json or markdown"),
    ):
        memories = memory_store.export_project(project)

        if format == "markdown":
            lines = [f"# {project} — Memory Export\n"]
            lines.append(f"Exported: {datetime.now(timezone.utc).isoformat()}")
            lines.append(f"Total memories: {len(memories)}\n")

            for m in memories:
                lines.append(f"---\n")
                lines.append(f"## Memory #{m['id']} — {m['memory_type']}")
                lines.append(f"**Importance:** {m['importance']}")
                lines.append(f"**Created:** {m['created_at']}")
                if m["summary"]:
                    lines.append(f"**Summary:** {m['summary']}")
                if m["tags"]:
                    lines.append(f"**Tags:** {', '.join(m['tags'])}")
                if m["related_files"]:
                    lines.append(f"**Files:** {', '.join(m['related_files'])}")
                lines.append(f"\n{m['content']}\n")

            content = "\n".join(lines)
            return Response(
                content=content,
                media_type="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="{project}-export.md"'},
            )

        return {
            "project": project,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "memory_count": len(memories),
            "memories": memories,
        }

    app.include_router(router)
    return app
