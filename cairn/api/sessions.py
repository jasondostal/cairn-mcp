"""Session endpoints — list, events, close."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Path

from cairn.core.services import Services

logger = logging.getLogger(__name__)


def register_routes(router: APIRouter, svc: Services, **kw):
    event_bus = svc.event_bus
    db = svc.db

    @router.get("/sessions")
    def api_sessions(
        project: str | None = Query(None),
        active_only: bool = Query(False),
        limit: int = Query(20, ge=1, le=100),
    ):
        """List sessions from the sessions table."""
        result = event_bus.list_sessions(
            project=project, active_only=active_only, limit=limit,
        )

        return result

    @router.get("/sessions/{session_name}/events")
    def api_session_events(
        session_name: str = Path(...),
        project: str | None = Query(None),
        limit: int = Query(200, ge=1, le=1000),
        order: str = Query("asc", pattern="^(asc|desc)$"),
    ):
        """Get events for a session — delegates to event_bus.query()."""
        return event_bus.query(
            session_name=session_name, project=project, limit=limit,
            order=order,
        )

    @router.post("/sessions/{session_name}/close")
    def api_session_close(session_name: str = Path(...)):
        """Close a session. No digest, no synthesis — just set closed_at."""
        return event_bus.close_session(session_name)


