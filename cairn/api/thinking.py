"""Thinking sequence endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Path, HTTPException
from pydantic import BaseModel

from cairn.api.utils import parse_multi
from cairn.core.services import Services


class AddThoughtRequest(BaseModel):
    thought: str
    thought_type: str = "general"
    author: str | None = None
    branch_name: str | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    thinking_engine = svc.thinking_engine

    @router.get("/thinking")
    def api_thinking_list(
        project: str | None = Query(None),
        status: str | None = Query(None),
        limit: int | None = Query(None, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return thinking_engine.list_sequences(
            project=parse_multi(project), status=status, limit=limit, offset=offset,
        )

    @router.get("/thinking/{sequence_id}")
    def api_thinking_detail(sequence_id: int = Path(...)):
        try:
            return thinking_engine.get_sequence(sequence_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Thinking sequence not found")

    @router.post("/thinking/{sequence_id}/thoughts")
    def api_add_thought(sequence_id: int = Path(...), body: AddThoughtRequest = ...):
        try:
            return thinking_engine.add_thought(
                sequence_id, body.thought, body.thought_type, body.branch_name, body.author,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/thinking/{sequence_id}/reopen")
    def api_reopen_sequence(sequence_id: int = Path(...)):
        try:
            return thinking_engine.reopen(sequence_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
