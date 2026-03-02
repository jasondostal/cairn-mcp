"""Working memory REST API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Path, HTTPException
from pydantic import BaseModel

from cairn.api.utils import parse_multi
from cairn.core.services import Services


class CaptureRequest(BaseModel):
    content: str
    item_type: str = "thread"
    salience: float | None = None
    author: str | None = None
    session_name: str | None = None


class ResolveRequest(BaseModel):
    resolved_into: str
    resolution_id: str | None = None
    resolution_note: str | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    wm = svc.working_memory_store

    @router.get("/working-memory")
    def api_wm_list(
        project: str | None = Query(None),
        author: str | None = Query(None),
        item_type: str | None = Query(None),
        min_salience: float = Query(0.0, ge=0.0, le=1.0),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        projects = parse_multi(project)
        return wm.list_active(
            projects if projects else project,
            author=author,
            item_type=item_type,
            min_salience=min_salience,
            limit=limit,
            offset=offset,
        )

    @router.get("/working-memory/{item_id}")
    def api_wm_detail(item_id: int = Path(...)):
        result = wm.get(item_id)
        if not result or "error" in result:
            raise HTTPException(status_code=404, detail="Working memory item not found")
        return result

    @router.post("/working-memory")
    def api_wm_capture(
        project: str = Query(...),
        body: CaptureRequest = ...,
    ):
        return wm.capture(
            project, body.content,
            item_type=body.item_type,
            salience=body.salience,
            author=body.author,
            session_name=body.session_name,
        )

    @router.post("/working-memory/{item_id}/resolve")
    def api_wm_resolve(item_id: int = Path(...), body: ResolveRequest = ...):
        result = wm.resolve(
            item_id,
            resolved_into=body.resolved_into,
            resolution_id=body.resolution_id,
            resolution_note=body.resolution_note,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.post("/working-memory/{item_id}/boost")
    def api_wm_boost(item_id: int = Path(...)):
        result = wm.boost(item_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.post("/working-memory/{item_id}/pin")
    def api_wm_pin(item_id: int = Path(...)):
        result = wm.pin(item_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.post("/working-memory/{item_id}/unpin")
    def api_wm_unpin(item_id: int = Path(...)):
        result = wm.unpin(item_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.post("/working-memory/{item_id}/archive")
    def api_wm_archive(item_id: int = Path(...)):
        result = wm.archive(item_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
