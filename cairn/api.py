"""Cairn REST API — read-only endpoints for the web UI."""

from __future__ import annotations

import logging

from fastapi import FastAPI, APIRouter, Query, Path, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from cairn.core.status import get_status

logger = logging.getLogger(__name__)


def create_api(
    *,
    db,
    config,
    memory_store,
    search_engine,
    cluster_engine,
    project_manager,
    task_manager,
    thinking_engine,
) -> FastAPI:
    """Build the read-only REST API as a FastAPI app.

    Designed to be mounted as a sub-app on the MCP Starlette parent.
    No lifespan needed — the parent handles DB lifecycle.
    """
    app = FastAPI(
        title="Cairn API",
        version="0.2.0",
        description="Read-only REST API for the Cairn web UI.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten when Authentik is wired
        allow_methods=["GET"],
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
    # GET /search?q=&project=&type=&mode=&limit=
    # ------------------------------------------------------------------
    @router.get("/search")
    def api_search(
        q: str = Query(..., description="Search query"),
        project: str | None = Query(None),
        type: str | None = Query(None),
        mode: str = Query("semantic"),
        limit: int = Query(10, ge=1, le=100),
    ):
        return search_engine.search(
            query=q,
            project=project,
            memory_type=type,
            search_mode=mode,
            limit=limit,
            include_full=True,
        )

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
    # GET /projects — all projects with counts
    # ------------------------------------------------------------------
    @router.get("/projects")
    def api_projects():
        return project_manager.list_all()

    # ------------------------------------------------------------------
    # GET /projects/:name — project docs + links
    # ------------------------------------------------------------------
    @router.get("/projects/{name}")
    def api_project_detail(name: str = Path(...)):
        docs = project_manager.get_docs(name)
        links = project_manager.get_links(name)
        return {"name": name, "docs": docs, "links": links}

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
    # GET /tasks?project=&include_completed=
    # ------------------------------------------------------------------
    @router.get("/tasks")
    def api_tasks(
        project: str = Query(...),
        include_completed: bool = Query(False),
    ):
        return task_manager.list_tasks(project, include_completed=include_completed)

    # ------------------------------------------------------------------
    # GET /thinking?project=&status=
    # ------------------------------------------------------------------
    @router.get("/thinking")
    def api_thinking_list(
        project: str = Query(...),
        status: str | None = Query(None),
    ):
        return thinking_engine.list_sequences(project, status=status)

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
    # GET /rules?project=
    # ------------------------------------------------------------------
    @router.get("/rules")
    def api_rules(project: str | None = Query(None)):
        return memory_store.get_rules(project)

    app.include_router(router)
    return app
