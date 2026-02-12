"""Cairn REST API — endpoints for the web UI and content ingestion."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import Depends, FastAPI, APIRouter, Query, Path, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from cairn.core.constants import (
    MAX_EVENT_BATCH_SIZE,
    VALID_DOC_TYPES,
    VALID_MEMORY_TYPES,
)
from cairn.core.services import Services
from cairn.core.status import get_status
from cairn.core.utils import get_or_create_project

logger = logging.getLogger(__name__)


def parse_multi(param: str | None) -> list[str] | None:
    """Split a comma-separated query param into a list, or None if empty."""
    if not param:
        return None
    parts = [p.strip() for p in param.split(",") if p.strip()]
    return parts if parts else None


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Optional API key authentication middleware.

    When enabled, checks for a valid API key in the configured header.
    Allows OPTIONS requests (CORS preflight) and health/swagger endpoints through.
    """

    def __init__(self, app, api_key: str, header_name: str = "X-API-Key"):
        super().__init__(app)
        self.api_key = api_key
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        # Always allow CORS preflight, health, and docs
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path.rstrip("/")
        if path in ("/status", "/swagger", "/openapi.json",
                     "/api/status", "/api/swagger", "/api/openapi.json"):
            return await call_next(request)

        token = request.headers.get(self.header_name)
        if not token or token != self.api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
        return await call_next(request)


def create_api(svc: Services) -> FastAPI:
    """Build the REST API as a FastAPI app.

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
    ingest_pipeline = svc.ingest_pipeline
    def _release_db_conn():
        """Release DB connection after each API request.

        Read-only endpoints don't call commit/rollback, leaving connections
        checked out with stale transactions. This dependency runs after every
        request and returns the connection to the pool, preventing exhaustion.
        Write endpoints already call commit() which releases — this is a no-op
        in that case.
        """
        yield
        db.release_if_held()

    app = FastAPI(
        title="Cairn API",
        version="0.27.0",
        description="REST API for the Cairn web UI and content ingestion.",
        docs_url="/swagger",
        redoc_url=None,
        dependencies=[Depends(_release_db_conn)],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Optional API key auth
    if config.auth.enabled and config.auth.api_key:
        app.add_middleware(
            APIKeyAuthMiddleware,
            api_key=config.auth.api_key,
            header_name=config.auth.header_name,
        )
        logger.info("API key auth enabled (header: %s)", config.auth.header_name)

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
        projects = parse_multi(project)
        types = parse_multi(type)

        where = ["m.is_active = true", "m.created_at >= %s"]
        params: list = [cutoff]

        if projects:
            where.append("p.name = ANY(%s)")
            params.append(projects)
        if types:
            where.append("m.memory_type = ANY(%s)")
            params.append(types)

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
            project=parse_multi(project),
            memory_type=parse_multi(type),
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
    # GET /docs?project=&doc_type=&limit=&offset=
    # ------------------------------------------------------------------
    @router.get("/docs")
    def api_docs(
        project: str | None = Query(None),
        doc_type: str | None = Query(None),
        limit: int | None = Query(None, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return project_manager.list_all_docs(
            project=parse_multi(project), doc_type=parse_multi(doc_type), limit=limit, offset=offset,
        )

    # ------------------------------------------------------------------
    # GET /docs/:id — single document with full content
    # ------------------------------------------------------------------
    @router.get("/docs/{doc_id}")
    def api_doc_detail(doc_id: int = Path(...)):
        doc = project_manager.get_doc(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc

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
            project=parse_multi(project), include_completed=include_completed,
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
            project=parse_multi(project), status=status, limit=limit, offset=offset,
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
        return cairn_manager.stack(project=parse_multi(project), limit=limit)

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
        return memory_store.get_rules(parse_multi(project), limit=limit, offset=offset)

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

        # Fetch node details with cluster membership
        placeholders = ",".join(["%s"] * len(id_list))
        nodes_raw = db.execute(
            f"""
            SELECT m.id, m.summary, m.memory_type, m.importance,
                   m.created_at, m.updated_at,
                   p.name as project,
                   c.id as cluster_id, c.label as cluster_label
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            LEFT JOIN cluster_members cm ON cm.memory_id = m.id
            LEFT JOIN clusters c ON c.id = cm.cluster_id
            WHERE m.id IN ({placeholders})
            """,
            tuple(id_list),
        )

        now = datetime.now(timezone.utc)
        nodes = []
        for r in nodes_raw:
            updated = r["updated_at"] if r["updated_at"] else r["created_at"]
            age_days = (now - updated).days if updated else 0
            # Server-computed size: base 5 + importance * 8
            size = 5 + float(r["importance"]) * 8
            node = {
                "id": r["id"],
                "summary": r["summary"] or f"Memory #{r['id']}",
                "memory_type": r["memory_type"],
                "importance": float(r["importance"]),
                "project": r["project"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": updated.isoformat() if updated else r["created_at"].isoformat(),
                "cluster_id": r["cluster_id"],
                "cluster_label": r["cluster_label"],
                "age_days": age_days,
                "size": round(size, 1),
            }
            nodes.append(node)

        # Stats
        relation_counts: dict[str, int] = {}
        for e in edges:
            rel = e["relation"]
            relation_counts[rel] = relation_counts.get(rel, 0) + 1

        # Relation colors for UI
        relation_colors = {
            "extends": "#3b82f6",
            "contradicts": "#ef4444",
            "implements": "#22c55e",
            "depends_on": "#f59e0b",
            "related": "#6b7280",
        }

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "relation_types": relation_counts,
                "relation_colors": relation_colors,
            },
        }

    # ------------------------------------------------------------------
    # GET /drift?project=
    # ------------------------------------------------------------------
    @router.get("/drift")
    def api_drift(
        project: str | None = Query(None),
    ):
        """Check for stale file references. Query params only — for quick dashboard checks.
        For full drift checks with file hashes, use POST /drift.
        """
        return svc.drift_detector.check(project=project, files=None)

    @router.post("/drift")
    def api_drift_post(body: dict):
        """Full drift check: compare stored hashes against current file hashes."""
        project = body.get("project")
        files = body.get("files")
        return svc.drift_detector.check(project=project, files=files)

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

    # ------------------------------------------------------------------
    # POST /events/ingest — ingest a batch of session events (from hooks)
    # ------------------------------------------------------------------
    @router.post("/events/ingest", status_code=202)
    def api_events_ingest(body: dict):
        project = body.get("project")
        session_name = body.get("session_name")
        batch_number = body.get("batch_number")
        events = body.get("events", [])

        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        if not session_name:
            raise HTTPException(status_code=400, detail="session_name is required")
        if batch_number is None:
            raise HTTPException(status_code=400, detail="batch_number is required")
        if not isinstance(events, list) or len(events) == 0:
            raise HTTPException(status_code=400, detail="events must be a non-empty array")
        if len(events) > MAX_EVENT_BATCH_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"batch exceeds max size of {MAX_EVENT_BATCH_SIZE} events",
            )

        import json
        project_id = get_or_create_project(db, project)

        # Upsert: if batch already exists, return idempotent response
        existing = db.execute_one(
            "SELECT id FROM session_events WHERE project_id = %s AND session_name = %s AND batch_number = %s",
            (project_id, session_name, batch_number),
        )
        if existing:
            return {"status": "already_ingested", "batch_id": existing["id"]}

        row = db.execute_one(
            """
            INSERT INTO session_events (project_id, session_name, batch_number, raw_events, event_count)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            RETURNING id
            """,
            (project_id, session_name, batch_number, json.dumps(events), len(events)),
        )
        db.commit()

        return {"status": "ingested", "batch_id": row["id"], "event_count": len(events)}

    # ------------------------------------------------------------------
    # GET /events?session_name=&project= — list event batches with digest status
    # ------------------------------------------------------------------
    @router.get("/events")
    def api_events(
        session_name: str = Query(..., description="Session name"),
        project: str | None = Query(None),
    ):
        where = ["se.session_name = %s"]
        params: list = [session_name]

        if project:
            where.append("p.name = %s")
            params.append(project)

        where_clause = " AND ".join(where)

        rows = db.execute(
            f"""
            SELECT se.id, se.session_name, se.batch_number, se.event_count,
                   se.digest, se.digested_at, se.created_at, p.name as project
            FROM session_events se
            LEFT JOIN projects p ON se.project_id = p.id
            WHERE {where_clause}
            ORDER BY se.batch_number ASC
            """,
            tuple(params),
        )

        items = [
            {
                "id": r["id"],
                "session_name": r["session_name"],
                "batch_number": r["batch_number"],
                "event_count": r["event_count"],
                "digest": r["digest"],
                "digested": r["digest"] is not None,
                "digested_at": r["digested_at"].isoformat() if r["digested_at"] else None,
                "project": r["project"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]

        return {
            "session_name": session_name,
            "batch_count": len(items),
            "digested_count": sum(1 for i in items if i["digested"]),
            "items": items,
        }

    # ==================================================================
    # INGEST — write endpoints for content ingestion
    # ==================================================================

    # ------------------------------------------------------------------
    # POST /ingest/doc — create a single project document
    # ------------------------------------------------------------------
    @router.post("/ingest/doc", status_code=201)
    def api_ingest_doc(body: dict):
        project = body.get("project")
        doc_type = body.get("doc_type")
        content = body.get("content")
        title = body.get("title")

        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        if not doc_type:
            raise HTTPException(status_code=400, detail="doc_type is required")
        if doc_type not in VALID_DOC_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid doc_type: {doc_type}. Must be one of: {VALID_DOC_TYPES}",
            )
        if not content:
            raise HTTPException(status_code=400, detail="content is required")

        result = project_manager.create_doc(project, doc_type, content, title=title)
        return result

    # ------------------------------------------------------------------
    # POST /ingest/docs — batch create multiple project documents
    # ------------------------------------------------------------------
    @router.post("/ingest/docs", status_code=201)
    def api_ingest_docs(body: dict):
        documents = body.get("documents")

        if not isinstance(documents, list) or len(documents) == 0:
            raise HTTPException(status_code=400, detail="documents must be a non-empty array")

        results = []
        errors = []
        for i, doc in enumerate(documents):
            project = doc.get("project")
            doc_type = doc.get("doc_type")
            content = doc.get("content")
            title = doc.get("title")

            if not project or not doc_type or not content:
                errors.append({"index": i, "error": "project, doc_type, and content are required"})
                continue
            if doc_type not in VALID_DOC_TYPES:
                errors.append({"index": i, "error": f"Invalid doc_type: {doc_type}"})
                continue

            try:
                result = project_manager.create_doc(project, doc_type, content, title=title)
                results.append(result)
            except Exception as e:
                logger.exception("Failed to create doc at index %d", i)
                errors.append({"index": i, "error": str(e)})

        return {"created": len(results), "errors": errors, "results": results}

    # ------------------------------------------------------------------
    # POST /ingest/memory — store a memory via REST (bypasses MCP)
    # ------------------------------------------------------------------
    @router.post("/ingest/memory", status_code=201)
    def api_ingest_memory(body: dict):
        content = body.get("content")
        project = body.get("project")
        memory_type = body.get("memory_type", "note")
        importance = body.get("importance", 0.5)
        tags = body.get("tags")
        session_name = body.get("session_name")
        related_files = body.get("related_files")
        related_ids = body.get("related_ids")

        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        if memory_type not in VALID_MEMORY_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid memory_type: {memory_type}. Must be one of: {VALID_MEMORY_TYPES}",
            )
        if not isinstance(importance, (int, float)) or not (0.0 <= importance <= 1.0):
            raise HTTPException(status_code=400, detail="importance must be a number between 0.0 and 1.0")

        result = memory_store.store(
            content=content,
            project=project,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            session_name=session_name,
            related_files=related_files,
            related_ids=related_ids,
        )
        return result

    # ------------------------------------------------------------------
    # POST /ingest — smart ingestion: classify, chunk, dedup, route
    # ------------------------------------------------------------------
    @router.post("/ingest", status_code=201)
    def api_ingest(body: dict):
        content = body.get("content")
        project = body.get("project")
        url = body.get("url")
        hint = body.get("hint", "auto")

        if not content and not url:
            raise HTTPException(status_code=400, detail="content or url is required")
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        if hint not in ("auto", "doc", "memory", "both"):
            raise HTTPException(status_code=400, detail="hint must be one of: auto, doc, memory, both")

        doc_type = body.get("doc_type")
        if doc_type and doc_type not in VALID_DOC_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid doc_type: {doc_type}. Must be one of: {VALID_DOC_TYPES}",
            )

        memory_type = body.get("memory_type")
        if memory_type and memory_type not in VALID_MEMORY_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid memory_type: {memory_type}. Must be one of: {VALID_MEMORY_TYPES}",
            )

        try:
            result = ingest_pipeline.ingest(
                content=content,
                project=project,
                hint=hint,
                doc_type=doc_type,
                title=body.get("title"),
                source=body.get("source"),
                tags=body.get("tags"),
                session_name=body.get("session_name"),
                url=url,
                memory_type=memory_type,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        if result["status"] == "duplicate":
            return JSONResponse(content=result, status_code=200)
        return result

    # ------------------------------------------------------------------
    # GET /bookmarklet.js — browser bookmarklet for quick capture
    # ------------------------------------------------------------------
    @router.get("/bookmarklet.js")
    def api_bookmarklet():
        js = (
            "javascript:void(window.open("
            "'https://cairn.witekdivers.com/capture"
            "?url='+encodeURIComponent(location.href)"
            "+'&title='+encodeURIComponent(document.title)"
            "+'&text='+encodeURIComponent(window.getSelection().toString()),"
            "'_blank','width=600,height=600'))"
        )
        return Response(content=js, media_type="application/javascript")

    # ------------------------------------------------------------------
    # Analytics endpoints
    # ------------------------------------------------------------------
    analytics_engine = svc.analytics_engine

    if analytics_engine:
        @router.get("/analytics/overview")
        def api_analytics_overview(
            days: int = Query(7, ge=1, le=365),
        ):
            return analytics_engine.overview(days=days)

        @router.get("/analytics/timeseries")
        def api_analytics_timeseries(
            days: int = Query(7, ge=1, le=365),
            granularity: str = Query("hour"),
            project: str | None = Query(None),
            operation: str | None = Query(None),
        ):
            if granularity not in ("hour", "day"):
                granularity = "hour"
            return analytics_engine.timeseries(
                days=days, granularity=granularity,
                project=project, operation=operation,
            )

        @router.get("/analytics/operations")
        def api_analytics_operations(
            days: int = Query(7, ge=1, le=365),
            project: str | None = Query(None),
            operation: str | None = Query(None),
            success: bool | None = Query(None),
            limit: int = Query(50, ge=1, le=200),
            offset: int = Query(0, ge=0),
        ):
            return analytics_engine.operations(
                days=days, project=project, operation=operation,
                success=success, limit=limit, offset=offset,
            )

        @router.get("/analytics/projects")
        def api_analytics_projects(
            days: int = Query(7, ge=1, le=365),
        ):
            return analytics_engine.projects_breakdown(days=days)

        @router.get("/analytics/models")
        def api_analytics_models(
            days: int = Query(7, ge=1, le=365),
        ):
            return analytics_engine.models_performance(days=days)

        @router.get("/analytics/memory-growth")
        def api_analytics_memory_growth(
            days: int = Query(90, ge=1, le=365),
            granularity: str = Query("day"),
        ):
            if granularity not in ("hour", "day"):
                granularity = "day"
            return analytics_engine.memory_type_growth(days=days, granularity=granularity)

        @router.get("/analytics/sparklines")
        def api_analytics_sparklines(
            days: int = Query(30, ge=1, le=365),
        ):
            return analytics_engine.entity_counts_sparkline(days=days)

        @router.get("/analytics/heatmap")
        def api_analytics_heatmap(
            days: int = Query(365, ge=1, le=365),
        ):
            return analytics_engine.activity_heatmap(days=days)

    app.include_router(router)
    return app
