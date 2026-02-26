"""Audit trail endpoints — read-only access to the immutable audit log."""

from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException

from cairn.core.services import Services


def register_routes(router: APIRouter, svc: Services, **kw):
    audit = svc.audit_manager

    if not audit:
        return

    @router.get("/audit")
    def api_audit_query(
        trace_id: str | None = Query(None),
        actor: str | None = Query(None),
        action: str | None = Query(None),
        resource_type: str | None = Query(None),
        resource_id: int | None = Query(None),
        project: str | None = Query(None),
        days: int | None = Query(None, ge=1, le=365),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return audit.query(
            trace_id=trace_id,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            project=project,
            days=days,
            limit=limit,
            offset=offset,
        )

    @router.get("/audit/trace/{trace_id}")
    def api_audit_by_trace(trace_id: str):
        return audit.query(trace_id=trace_id, limit=200)

    @router.get("/audit/{audit_id}")
    def api_audit_get(audit_id: int):
        entry = audit.get(audit_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Audit entry not found")
        return entry
