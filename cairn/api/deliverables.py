"""Deliverable REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Path, Query
from pydantic import BaseModel

from cairn.core.services import Services


class CreateDeliverableBody(BaseModel):
    summary: str
    changes: list[dict] | None = None
    decisions: list[dict] | None = None
    open_items: list[dict] | None = None
    metrics: dict | None = None
    status: str = "draft"


class ReviewDeliverableBody(BaseModel):
    action: str  # approve, revise, reject
    reviewer: str | None = None
    notes: str | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    dm = svc.deliverable_manager

    @router.get("/deliverables/pending")
    def api_pending_deliverables(
        project: str | None = Query(None),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return dm.list_pending(project=project, limit=limit, offset=offset)

    @router.get("/work-items/{item_id}/deliverable")
    def api_get_deliverable(
        item_id: int = Path(...),
        version: int | None = Query(None),
    ):
        result = dm.get(item_id, version=version)
        if not result:
            return {"error": "No deliverable found", "work_item_id": item_id}
        return result

    @router.get("/work-items/{item_id}/deliverables")
    def api_list_deliverables(item_id: int = Path(...)):
        return dm.list_for_work_item(item_id)

    @router.post("/work-items/{item_id}/deliverable")
    def api_create_deliverable(
        item_id: int = Path(...),
        body: CreateDeliverableBody = Body(...),
    ):
        return dm.create(
            work_item_id=item_id,
            summary=body.summary,
            changes=body.changes,
            decisions=body.decisions,
            open_items=body.open_items,
            metrics=body.metrics,
            status=body.status,
        )

    @router.post("/work-items/{item_id}/deliverable/submit")
    def api_submit_deliverable(item_id: int = Path(...)):
        return dm.submit_for_review(item_id)

    @router.post("/work-items/{item_id}/deliverable/review")
    def api_review_deliverable(
        item_id: int = Path(...),
        body: ReviewDeliverableBody = Body(...),
    ):
        return dm.review(
            work_item_id=item_id,
            action=body.action,
            reviewer=body.reviewer,
            notes=body.notes,
        )
