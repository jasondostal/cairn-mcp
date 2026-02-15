"""Task endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Path

from cairn.api.utils import parse_multi
from cairn.core.services import Services


def register_routes(router: APIRouter, svc: Services, **kw):
    task_manager = svc.task_manager

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

    @router.post("/tasks/{task_id}/complete")
    def api_task_complete(task_id: int = Path(...)):
        task_manager.complete(task_id)
        return {"status": "ok"}
