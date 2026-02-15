"""Session endpoints — list, events, close with synthesis."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Path

from cairn.core.services import Services

logger = logging.getLogger(__name__)


def register_routes(router: APIRouter, svc: Services, **kw):
    db = svc.db
    digest_worker = svc.digest_worker
    memory_store = svc.memory_store

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
                   MAX(se.closed_at) as closed_at,
                   MAX(se.closed_at) IS NULL as is_active
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
                "closed_at": r["closed_at"].isoformat() if r["closed_at"] else None,
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
        """Close a session: digest pending batches, synthesize, conditionally store.

        Pipeline: digest remaining batches → gather all digests → LLM synthesis →
        significance filter → conditionally store ONE memory + extraction.
        """
        # 1. Digest any pending batches
        pending_rows = db.execute(
            """
            SELECT se.id, se.batch_number
            FROM session_events se
            WHERE se.session_name = %s AND se.digest IS NULL
            ORDER BY se.batch_number ASC
            """,
            (session_name,),
        )

        digested = 0
        for row in pending_rows:
            result = digest_worker.digest_immediate(row["id"])
            if result:
                digested += 1

        # 2. Gather ALL digests for this session
        all_rows = db.execute(
            """
            SELECT se.batch_number, se.digest, se.event_count, p.name as project
            FROM session_events se
            LEFT JOIN projects p ON se.project_id = p.id
            WHERE se.session_name = %s AND se.digest IS NOT NULL
            ORDER BY se.batch_number ASC
            """,
            (session_name,),
        )

        if not all_rows:
            # Mark closed even if no digests
            _mark_session_closed(db, session_name)
            return {
                "session_name": session_name,
                "pending_batches": len(pending_rows),
                "digested": digested,
                "synthesis": None,
            }

        project_name = all_rows[0]["project"] or "unknown"
        total_events = sum(r["event_count"] for r in all_rows)
        digests = [
            {"batch_number": r["batch_number"], "digest": r["digest"]}
            for r in all_rows
        ]

        # 3. Synthesize all digests into one session narrative
        synthesis = _synthesize_session(
            db, memory_store, digest_worker,
            session_name, project_name, digests, total_events,
        )

        # 4. Mark session closed
        _mark_session_closed(db, session_name, synthesis=synthesis)

        return {
            "session_name": session_name,
            "pending_batches": len(pending_rows),
            "digested": digested,
            "synthesis": synthesis,
        }


def _synthesize_session(
    db, memory_store, digest_worker,
    session_name: str, project: str,
    digests: list[dict], total_events: int,
) -> dict | None:
    """Run LLM synthesis on batch digests, conditionally store as memory.

    Returns the parsed synthesis result or None on failure.
    """
    from cairn.llm.prompts import build_digest_synthesis_messages

    if not digest_worker.can_digest():
        logger.warning("Session synthesis skipped: LLM unavailable for %s", session_name)
        return None

    messages = build_digest_synthesis_messages(digests, project, session_name, total_events)

    try:
        raw = digest_worker.llm.generate(messages, max_tokens=1024)
    except Exception:
        logger.warning("Session synthesis LLM call failed for %s", session_name, exc_info=True)
        return None

    if not raw or not raw.strip():
        return None

    # Parse structured JSON response
    import json as _json
    try:
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        synthesis = _json.loads(text)
    except (_json.JSONDecodeError, ValueError):
        logger.warning("Session synthesis returned non-JSON for %s: %s", session_name, raw[:200])
        # Fallback: treat as medium significance freeform summary
        synthesis = {
            "significance": "medium",
            "summary": raw.strip()[:500],
            "decisions": [],
            "outcomes": [],
            "discoveries": [],
            "dead_ends": [],
            "open_threads": [],
        }

    significance = synthesis.get("significance", "medium")
    summary = synthesis.get("summary", "")

    # 4. Conditionally store memory based on significance
    if significance in ("medium", "high") and summary and memory_store:
        # Build rich content from structured synthesis
        content_parts = [f"# Session: {session_name}\n\n{summary}"]

        for key, label in [
            ("decisions", "Decisions"),
            ("outcomes", "Outcomes"),
            ("discoveries", "Discoveries"),
            ("dead_ends", "Dead Ends"),
            ("open_threads", "Open Threads"),
        ]:
            items = synthesis.get(key, [])
            if items:
                content_parts.append(f"\n## {label}")
                for item in items:
                    content_parts.append(f"- {item}")

        content = "\n".join(content_parts)

        importance = 0.5 if significance == "medium" else 0.7

        # Determine memory type from content
        memory_type = "progress"
        if synthesis.get("decisions"):
            memory_type = "decision"
        elif synthesis.get("discoveries"):
            memory_type = "learning"

        try:
            memory_store.store(
                content=content,
                project=project,
                memory_type=memory_type,
                importance=importance,
                tags=["session-synthesis", f"significance-{significance}"],
                session_name=session_name,
                author="system",
            )
            logger.info(
                "Session synthesis stored for %s: significance=%s, type=%s",
                session_name, significance, memory_type,
            )
        except Exception:
            logger.warning("Failed to store session synthesis for %s", session_name, exc_info=True)
    else:
        logger.info("Session synthesis skipped storage for %s: significance=%s", session_name, significance)

    return synthesis


def _mark_session_closed(db, session_name: str, synthesis: dict | None = None) -> None:
    """Set closed_at on all batches for this session."""
    now = datetime.now(timezone.utc)
    synthesis_json = json.dumps(synthesis) if synthesis else None
    db.execute(
        """
        UPDATE session_events
        SET closed_at = %s, synthesis = %s::jsonb
        WHERE session_name = %s AND closed_at IS NULL
        """,
        (now, synthesis_json, session_name),
    )
    db.commit()
