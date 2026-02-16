"""Work item REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Path, Query
from pydantic import BaseModel

from cairn.core.services import Services


class CreateWorkItemBody(BaseModel):
    project: str
    title: str
    description: str | None = None
    item_type: str = "task"
    priority: int = 0
    parent_id: int | None = None
    session_name: str | None = None
    metadata: dict | None = None
    acceptance_criteria: str | None = None


class UpdateWorkItemBody(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    assignee: str | None = None
    item_type: str | None = None
    session_name: str | None = None
    metadata: dict | None = None
    acceptance_criteria: str | None = None


class ClaimBody(BaseModel):
    assignee: str


class AddChildBody(BaseModel):
    title: str
    description: str | None = None
    priority: int = 0
    session_name: str | None = None
    metadata: dict | None = None
    acceptance_criteria: str | None = None


class BlockBody(BaseModel):
    blocker_id: int
    blocked_id: int


class LinkMemoriesBody(BaseModel):
    memory_ids: list[int]


def register_routes(router: APIRouter, svc: Services, **kw):
    wim = svc.work_item_manager

    @router.get("/work-items")
    def api_list_work_items(
        project: str | None = Query(None),
        status: str | None = Query(None),
        item_type: str | None = Query(None),
        assignee: str | None = Query(None),
        parent_id: int | None = Query(None),
        include_children: bool = Query(False),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return wim.list_items(
            project=project, status=status, item_type=item_type,
            assignee=assignee, parent_id=parent_id,
            include_children=include_children, limit=limit, offset=offset,
        )

    @router.get("/work-items/ready")
    def api_ready_queue(
        project: str = Query(...),
        limit: int = Query(10, ge=1, le=100),
    ):
        return wim.ready_queue(project, limit=limit)

    @router.get("/work-items/{item_id}")
    def api_get_work_item(item_id: int = Path(...)):
        return wim.get(item_id)

    @router.post("/work-items")
    def api_create_work_item(body: CreateWorkItemBody):
        return wim.create(
            project=body.project, title=body.title, description=body.description,
            item_type=body.item_type, priority=body.priority,
            parent_id=body.parent_id, session_name=body.session_name,
            metadata=body.metadata, acceptance_criteria=body.acceptance_criteria,
        )

    @router.patch("/work-items/{item_id}")
    def api_update_work_item(item_id: int = Path(...), body: UpdateWorkItemBody = Body(...)):
        fields = body.model_dump(exclude_none=True)
        if not fields:
            return {"id": item_id, "action": "no_changes"}
        return wim.update(item_id, **fields)

    @router.post("/work-items/{item_id}/claim")
    def api_claim_work_item(item_id: int = Path(...), body: ClaimBody = Body(...)):
        return wim.claim(item_id, body.assignee)

    @router.post("/work-items/{item_id}/complete")
    def api_complete_work_item(item_id: int = Path(...)):
        return wim.complete(item_id)

    @router.post("/work-items/{item_id}/children")
    def api_add_child(item_id: int = Path(...), body: AddChildBody = Body(...)):
        return wim.add_child(
            parent_id=item_id, title=body.title, description=body.description,
            priority=body.priority, session_name=body.session_name,
            metadata=body.metadata, acceptance_criteria=body.acceptance_criteria,
        )

    @router.post("/work-items/block")
    def api_block(body: BlockBody = Body(...)):
        return wim.block(body.blocker_id, body.blocked_id)

    @router.delete("/work-items/block")
    def api_unblock(body: BlockBody = Body(...)):
        return wim.unblock(body.blocker_id, body.blocked_id)

    @router.post("/work-items/{item_id}/link-memories")
    def api_link_memories(item_id: int = Path(...), body: LinkMemoriesBody = Body(...)):
        return wim.link_memories(item_id, body.memory_ids)
