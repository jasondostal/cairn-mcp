"""Ingestion endpoints — memory, document, smart ingest, bookmarklet."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from cairn.core.constants import VALID_DOC_TYPES, VALID_MEMORY_TYPES
from cairn.core.services import Services

logger = logging.getLogger(__name__)


def register_routes(router: APIRouter, svc: Services, **kw):
    db = svc.db
    memory_store = svc.memory_store
    project_manager = svc.project_manager
    ingest_pipeline = svc.ingest_pipeline

    # /events/ingest and /events GET removed in v0.50.0 — use /events from cairn.api.events

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

        return project_manager.create_doc(project, doc_type, content, title=title)

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

        return memory_store.store(
            content=content,
            project=project,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            session_name=session_name,
            related_files=related_files,
            related_ids=related_ids,
        )

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

    @router.get("/bookmarklet.js")
    def api_bookmarklet(request: Request):
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost:3000"))
        base = f"{scheme}://{host}"
        js = (
            "javascript:void(window.open("
            f"'{base}/capture"
            "?url='+encodeURIComponent(location.href)"
            "+'&title='+encodeURIComponent(document.title)"
            "+'&text='+encodeURIComponent(window.getSelection().toString()),"
            "'_blank','width=600,height=600'))"
        )
        return Response(content=js, media_type="application/javascript")
