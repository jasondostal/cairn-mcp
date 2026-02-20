"""Deprecated endpoints — kept for backward compatibility during transition."""

from __future__ import annotations

from fastapi import APIRouter, Query, Path

from cairn.core.services import Services


def register_routes(router: APIRouter, svc: Services, **kw):

    @router.get("/cairns")
    def api_cairns(
        project: str | None = Query(None),
        limit: int = Query(20, ge=1, le=50),
    ):
        return {"deprecated": "Cairns removed in v0.37.0. Use orient() tool for boot orientation."}

    @router.post("/cairns")
    def api_set_cairn(body: dict):
        # Accept silently during transition — hooks may still call this
        return {"status": "accepted", "deprecated": "Cairns removed in v0.37.0"}

    @router.get("/cairns/{cairn_id}")
    def api_cairn_detail(cairn_id: int = Path(...)):
        return {"deprecated": "Cairns removed in v0.37.0"}
