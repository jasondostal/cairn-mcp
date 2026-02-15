"""Session endpoints — list, events, close."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, Path

from cairn.core.services import Services

logger = logging.getLogger(__name__)


def register_routes(router: APIRouter, svc: Services, **kw):
    db = svc.db
    digest_worker = svc.digest_worker

    @router.get("/sessions")
    def api_sessions(
        project: str | None = Query(None),
        limit: int = Query(20, ge=1, le=100),
    ):
        where_parts = []
        params: list = []

        if project:
            where_parts.append("p.name = %s")
            params.append(project)

        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        rows = db.execute(
            f"""
            SELECT se.session_name,
                   p.name as project,
                   COUNT(*) as batch_count,
                   SUM(se.event_count) as total_events,
                   COUNT(*) FILTER (WHERE se.digest IS NOT NULL) as digested_count,
                   MIN(se.created_at) as first_event,
                   MAX(se.created_at) as last_event,
                   MAX(se.created_at) > NOW() - INTERVAL '2 hours' as is_active
            FROM session_events se
            LEFT JOIN projects p ON se.project_id = p.id
            {where_clause}
            GROUP BY se.session_name, p.name
            ORDER BY MAX(se.created_at) DESC
            LIMIT %s
            """,
            tuple(params) + (limit,),
        )

        items = [
            {
                "session_name": r["session_name"],
                "project": r["project"],
                "batch_count": r["batch_count"],
                "total_events": r["total_events"],
                "digested_count": r["digested_count"],
                "first_event": r["first_event"].isoformat() if r["first_event"] else None,
                "last_event": r["last_event"].isoformat() if r["last_event"] else None,
                "is_active": r["is_active"],
            }
            for r in rows
        ]

        return {"count": len(items), "items": items}

    @router.get("/sessions/{session_name}/events")
    def api_session_events(
        session_name: str = Path(...),
        project: str | None = Query(None),
    ):
        where = ["se.session_name = %s"]
        params: list = [session_name]
        if project:
            where.append("p.name = %s")
            params.append(project)

        rows = db.execute(
            f"""
            SELECT se.batch_number, se.raw_events, se.event_count,
                   se.digest, se.digested_at, se.created_at, p.name as project
            FROM session_events se
            LEFT JOIN projects p ON se.project_id = p.id
            WHERE {" AND ".join(where)}
            ORDER BY se.batch_number ASC
            """,
            tuple(params),
        )

        events = []
        for r in rows:
            raw = r["raw_events"]
            if isinstance(raw, str):
                raw = json.loads(raw)
            for evt in (raw or []):
                events.append(evt)

        digests = [
            {"batch": r["batch_number"], "digest": r["digest"], "digested_at": r["digested_at"].isoformat() if r["digested_at"] else None}
            for r in rows if r["digest"]
        ]

        return {
            "session_name": session_name,
            "project": rows[0]["project"] if rows else None,
            "batch_count": len(rows),
            "total_events": len(events),
            "events": events,
            "digests": digests,
        }

    @router.post("/sessions/{session_name}/close")
    def api_session_close(session_name: str = Path(...)):
        """Close a session: digest any pending batches immediately."""
        rows = db.execute(
            """
            SELECT se.id, se.batch_number
            FROM session_events se
            WHERE se.session_name = %s AND se.digest IS NULL
            ORDER BY se.batch_number ASC
            """,
            (session_name,),
        )

        digested = 0
        for row in rows:
            result = digest_worker.digest_immediate(row["id"])
            if result:
                project_row = db.execute_one(
                    """
                    SELECT p.name FROM session_events se
                    LEFT JOIN projects p ON se.project_id = p.id
                    WHERE se.id = %s
                    """,
                    (row["id"],),
                )
                project_name = project_row["name"] if project_row and project_row["name"] else "unknown"
                digest_worker._store_digest_memory(result, project_name, session_name, row["batch_number"])
                digested += 1

        return {
            "session_name": session_name,
            "pending_batches": len(rows),
            "digested": digested,
        }
