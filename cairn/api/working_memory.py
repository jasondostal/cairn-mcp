"""Working memory REST API endpoints.

ca-173: Delegates to MemoryStore (unified memory). Working memory items are
now stored in the memories table with salience-based lifecycle.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel

from cairn.core.services import Services


class CaptureRequest(BaseModel):
    content: str
    item_type: str = "thread"
    salience: float | None = None
    author: str | None = None
    session_name: str | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    ms = svc.memory_store

    @router.get("/working-memory")
    def api_wm_list(
        project: str | None = Query(None),
        limit: int = Query(20, ge=1, le=100),
    ):
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        return {"items": ms.orient_items(project, limit=limit)}

    @router.get("/working-memory/{item_id}")
    def api_wm_detail(item_id: int = Path(...)):
        results = ms.recall([item_id])
        if not results:
            raise HTTPException(status_code=404, detail="Working memory item not found")
        return results[0]

    @router.post("/working-memory")
    def api_wm_capture(
        project: str = Query(...),
        body: CaptureRequest = Body(...),
    ):
        return ms.store(
            content=body.content,
            project=project,
            memory_type=body.item_type,
            salience=body.salience,
            author=body.author,
            session_name=body.session_name,
        )

    @router.post("/working-memory/{item_id}/resolve")
    def api_wm_resolve(item_id: int = Path(...)):
        result = ms.modify(item_id, action="graduate")
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.post("/working-memory/{item_id}/boost")
    def api_wm_boost(item_id: int = Path(...)):
        result = ms.modify(item_id, action="boost")
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.post("/working-memory/{item_id}/pin")
    def api_wm_pin(item_id: int = Path(...)):
        result = ms.modify(item_id, action="pin")
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.post("/working-memory/{item_id}/unpin")
    def api_wm_unpin(item_id: int = Path(...)):
        result = ms.modify(item_id, action="unpin")
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.post("/working-memory/{item_id}/archive")
    def api_wm_archive(item_id: int = Path(...)):
        result = ms.modify(item_id, action="inactivate", reason="archived via working_memory API")
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
