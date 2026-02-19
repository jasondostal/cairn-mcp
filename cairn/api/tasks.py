"""Task endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Path, HTTPException

from cairn.api.utils import parse_multi
from cairn.core.constants import ActivityType
from cairn.core.services import Services


def register_routes(router: APIRouter, svc: Services, **kw):
    task_manager = svc.task_manager
    work_item_manager = svc.work_item_manager
    db = svc.db

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

    @router.post("/tasks")
    def api_task_create(body: dict):
        return task_manager.create(
            project=body["project"], description=body["description"],
        )

    @router.post("/tasks/{task_id}/complete")
    def api_task_complete(task_id: int = Path(...)):
        task_manager.complete(task_id)
        return {"status": "ok"}

    @router.post("/tasks/{task_id}/promote")
    def api_task_promote(task_id: int = Path(...)):
        """Promote a personal task to a work item."""
        task_row = db.execute_one(
            """SELECT t.id, t.description, t.status, p.name AS project
               FROM tasks t
               LEFT JOIN projects p ON t.project_id = p.id
               WHERE t.id = %s""",
            (task_id,),
        )
        if not task_row:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        if task_row["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Task {task_id} is already {task_row['status']}",
            )

        project = task_row["project"]
        if not project:
            raise HTTPException(
                status_code=400, detail="Task has no project — cannot promote",
            )

        # Create work item from task
        wi = work_item_manager.create(
            project=project,
            title=task_row["description"],
            item_type="task",
        )

        # Mark task completed
        task_manager.complete(task_id)

        # Transfer linked memories
        linked = db.execute(
            "SELECT memory_id FROM task_memory_links WHERE task_id = %s",
            (task_id,),
        )
        linked_ids = [r["memory_id"] for r in linked]
        if linked_ids:
            work_item_manager.link_memories(wi["id"], linked_ids)

        # Log promoted activity
        work_item_manager._log_activity(
            wi["id"],
            actor="system",
            activity_type=ActivityType.PROMOTED,
            content=f"Promoted from task #{task_id}",
            metadata={"source_task_id": task_id},
        )

        return {"action": "promoted", "task_id": task_id, "work_item": wi}
