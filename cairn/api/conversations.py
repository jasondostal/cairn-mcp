"""Conversation REST endpoints for chat persistence."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from cairn.core.services import Services


class CreateConversationBody(BaseModel):
    project: str | None = None
    title: str | None = None
    model: str | None = None
    metadata: dict | None = None


class UpdateConversationBody(BaseModel):
    title: str


class AddMessageBody(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[dict] | None = None
    model: str | None = None
    token_count: int | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    mgr = svc.conversation_manager

    @router.get("/chat/conversations")
    def api_list_conversations(
        project: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return mgr.list(project=project, limit=limit, offset=offset)

    @router.post("/chat/conversations")
    def api_create_conversation(body: CreateConversationBody):
        return mgr.create(
            project=body.project,
            title=body.title,
            model=body.model,
            metadata=body.metadata,
        )

    @router.get("/chat/conversations/{conversation_id}")
    def api_get_conversation(conversation_id: int):
        conv = mgr.get(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv

    @router.patch("/chat/conversations/{conversation_id}")
    def api_update_conversation(conversation_id: int, body: UpdateConversationBody):
        conv = mgr.update_title(conversation_id, body.title)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv

    @router.delete("/chat/conversations/{conversation_id}")
    def api_delete_conversation(conversation_id: int):
        ok = mgr.delete(conversation_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"deleted": True, "id": conversation_id}

    @router.get("/chat/conversations/{conversation_id}/messages")
    def api_get_messages(
        conversation_id: int,
        limit: int = Query(200, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ):
        conv = mgr.get(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = mgr.get_messages(conversation_id, limit=limit, offset=offset)
        return {"conversation_id": conversation_id, "messages": messages}

    @router.post("/chat/conversations/{conversation_id}/messages")
    def api_add_message(conversation_id: int, body: AddMessageBody):
        conv = mgr.get(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return mgr.add_message(
            conversation_id=conversation_id,
            role=body.role,
            content=body.content,
            tool_calls=body.tool_calls,
            model=body.model,
            token_count=body.token_count,
        )
