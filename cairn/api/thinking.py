"""Thinking sequence endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Path, HTTPException

from cairn.api.utils import parse_multi
from cairn.core.services import Services


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
