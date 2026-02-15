"""Message endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Path, HTTPException

from cairn.api.utils import parse_multi
from cairn.core.services import Services


def register_routes(router: APIRouter, svc: Services, **kw):
    message_manager = svc.message_manager

    @router.get("/messages/unread-count")
    def api_messages_unread_count(
        project: str | None = Query(None),
    ):
        count = message_manager.unread_count(project=project)
        return {"count": count}

    @router.get("/messages")
    def api_messages(
        project: str | None = Query(None),
        include_archived: bool = Query(False),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return message_manager.inbox(
            project=parse_multi(project),
            include_archived=include_archived,
            limit=limit, offset=offset,
        )

    @router.post("/messages", status_code=201)
    def api_send_message(body: dict):
        content = body.get("content")
        project = body.get("project")
        sender = body.get("sender", "user")
        priority = body.get("priority", "normal")
        metadata = body.get("metadata")

        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        if priority not in ("normal", "urgent"):
            raise HTTPException(status_code=400, detail="priority must be 'normal' or 'urgent'")

        return message_manager.send(
            content=content, project=project,
            sender=sender, priority=priority,
            metadata=metadata,
        )

    @router.patch("/messages/{message_id}")
    def api_update_message(message_id: int = Path(...), body: dict | None = None):
        body = body or {}
        is_read = body.get("is_read")
        archived = body.get("archived")

        if is_read is True:
            message_manager.mark_read(message_id)
        if archived is True:
            message_manager.archive(message_id)

        return {"updated": True, "id": message_id}

    @router.post("/messages/mark-all-read")
    def api_mark_all_read(body: dict | None = None):
        body = body or {}
        project = body.get("project")
        return message_manager.mark_all_read(project=project)
