"""Cairn lifecycle management. Set, stack, get, and compress episodic markers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cairn.core.utils import get_or_create_project, extract_json

if TYPE_CHECKING:
    from cairn.config import LLMCapabilities
    from cairn.llm.interface import LLMInterface
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class CairnManager:
    """Manages episodic session markers (cairns).

    A cairn is set at the end of a session. It links all stones (memories)
    with a matching session_name, synthesizes a narrative, and marks the
    trail for future sessions to walk.
    """

    def __init__(
        self, db: Database, *,
        llm: LLMInterface | None = None,
        capabilities: LLMCapabilities | None = None,
    ):
        self.db = db
        self.llm = llm
        self.capabilities = capabilities

    def set(self, project: str, session_name: str, events: list | None = None) -> dict:
        """Set a cairn at the end of a session.

        Fetches all stones with matching session_name, synthesizes a title
        and narrative, creates the cairn record, and links the stones.

        Args:
            project: Project name.
            session_name: Session identifier (must match memories.session_name).
            events: Optional ordered event log (from hooks). Stored as JSONB.

        Returns:
            Dict with cairn details: id, title, narrative, memory_count, set_at.
        """
        from cairn.llm.prompts import build_cairn_narrative_messages

        project_id = get_or_create_project(self.db, project)

        # Check for existing cairn (idempotent — don't double-set)
        existing = self.db.execute_one(
            "SELECT id FROM cairns WHERE project_id = %s AND session_name = %s",
            (project_id, session_name),
        )
        if existing:
            return {"error": f"Cairn already exists for session '{session_name}' in project '{project}' (id={existing['id']})"}

        # Fetch session stones
        stones = self.db.execute(
            """
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.created_at
            FROM memories m
            WHERE m.project_id = %s AND m.session_name = %s AND m.is_active = true
            ORDER BY m.created_at ASC
            """,
            (project_id, session_name),
        )

        memory_count = len(stones)

        # Synthesize narrative via LLM (graceful degradation)
        # Synthesize when there are stones OR events (motes from hooks)
        title = None
        narrative = None
        has_content = memory_count > 0 or (events and len(events) > 0)
        can_synthesize = (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.session_synthesis
            and has_content
        )

        if can_synthesize:
            try:
                messages = build_cairn_narrative_messages(
                    stones, project, session_name, events=events,
                )
                raw = self.llm.generate(messages, max_tokens=1024)
                if raw and raw.strip():
                    parsed = extract_json(raw, json_type="object")
                    if parsed:
                        title = parsed.get("title")
                        narrative = parsed.get("narrative")
                    else:
                        # LLM returned text but not JSON — use as narrative
                        narrative = raw.strip()
            except Exception:
                logger.warning("Cairn narrative synthesis failed, setting without narrative", exc_info=True)

        # Fallback title if LLM didn't produce one
        if not title:
            title = f"Session: {session_name}" if memory_count > 0 else f"Empty session: {session_name}"

        now = datetime.now(timezone.utc)

        # Find earliest stone timestamp for started_at
        started_at = now
        if stones:
            first_ts = stones[0].get("created_at")
            if first_ts:
                started_at = first_ts

        # Create the cairn
        row = self.db.execute_one(
            """
            INSERT INTO cairns (project_id, session_name, title, narrative, events, memory_count, started_at, set_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            RETURNING id, title, narrative, memory_count, started_at, set_at
            """,
            (project_id, session_name, title, narrative,
             _json_or_none(events), memory_count, started_at, now),
        )

        cairn_id = row["id"]

        # Link stones to cairn
        if memory_count > 0:
            stone_ids = [s["id"] for s in stones]
            self.db.execute(
                "UPDATE memories SET cairn_id = %s WHERE id = ANY(%s)",
                (cairn_id, stone_ids),
            )

        self.db.commit()

        return {
            "id": cairn_id,
            "title": row["title"],
            "narrative": row["narrative"],
            "memory_count": row["memory_count"],
            "started_at": row["started_at"].isoformat() if hasattr(row["started_at"], "isoformat") else row["started_at"],
            "set_at": row["set_at"].isoformat() if hasattr(row["set_at"], "isoformat") else row["set_at"],
        }

    def stack(self, project: str, limit: int = 20) -> list[dict]:
        """View the trail — cairns for a project, newest first.

        Args:
            project: Project name.
            limit: Maximum cairns to return (default 20).

        Returns:
            List of cairn summaries ordered by set_at DESC.
        """
        project_id = get_or_create_project(self.db, project)

        rows = self.db.execute(
            """
            SELECT id, session_name, title, narrative, memory_count,
                   started_at, set_at, is_compressed
            FROM cairns
            WHERE project_id = %s AND set_at IS NOT NULL
            ORDER BY set_at DESC
            LIMIT %s
            """,
            (project_id, limit),
        )

        return [
            {
                "id": r["id"],
                "session_name": r["session_name"],
                "title": r["title"],
                "narrative": r["narrative"],
                "memory_count": r["memory_count"],
                "started_at": r["started_at"].isoformat() if hasattr(r["started_at"], "isoformat") else r["started_at"],
                "set_at": r["set_at"].isoformat() if hasattr(r["set_at"], "isoformat") else r["set_at"],
                "is_compressed": r["is_compressed"],
            }
            for r in rows
        ]

    def get(self, cairn_id: int) -> dict:
        """Examine a single cairn with full detail and linked stones.

        Args:
            cairn_id: The cairn ID.

        Returns:
            Full cairn detail including title, narrative, events, and all linked stones.

        Raises:
            ValueError: If cairn not found.
        """
        row = self.db.execute_one(
            """
            SELECT c.id, c.session_name, c.title, c.narrative, c.events,
                   c.memory_count, c.started_at, c.set_at, c.is_compressed,
                   p.name as project
            FROM cairns c
            LEFT JOIN projects p ON c.project_id = p.id
            WHERE c.id = %s
            """,
            (cairn_id,),
        )

        if not row:
            raise ValueError(f"Cairn {cairn_id} not found")

        # Fetch linked stones
        stones = self.db.execute(
            """
            SELECT id, summary, content, memory_type, importance, tags, created_at
            FROM memories
            WHERE cairn_id = %s AND is_active = true
            ORDER BY created_at ASC
            """,
            (cairn_id,),
        )

        stone_list = [
            {
                "id": s["id"],
                "summary": s.get("summary") or s["content"][:200],
                "memory_type": s["memory_type"],
                "importance": s["importance"],
                "tags": s["tags"],
                "created_at": s["created_at"].isoformat() if hasattr(s["created_at"], "isoformat") else s["created_at"],
            }
            for s in stones
        ]

        return {
            "id": row["id"],
            "project": row["project"],
            "session_name": row["session_name"],
            "title": row["title"],
            "narrative": row["narrative"],
            "events": row["events"],
            "memory_count": row["memory_count"],
            "started_at": row["started_at"].isoformat() if hasattr(row["started_at"], "isoformat") else row["started_at"],
            "set_at": row["set_at"].isoformat() if hasattr(row["set_at"], "isoformat") else row["set_at"],
            "is_compressed": row["is_compressed"],
            "stones": stone_list,
        }

    def compress(self, cairn_id: int) -> dict:
        """Clear event detail, keep narrative.

        Sets is_compressed = true and clears the events JSONB.
        Narrative and linked stones are preserved.

        Args:
            cairn_id: The cairn ID.

        Returns:
            Dict confirming compression with cairn ID and status.

        Raises:
            ValueError: If cairn not found.
        """
        row = self.db.execute_one(
            "SELECT id, is_compressed FROM cairns WHERE id = %s",
            (cairn_id,),
        )

        if not row:
            raise ValueError(f"Cairn {cairn_id} not found")

        if row["is_compressed"]:
            return {"id": cairn_id, "status": "already_compressed"}

        self.db.execute(
            "UPDATE cairns SET events = NULL, is_compressed = true WHERE id = %s",
            (cairn_id,),
        )
        self.db.commit()

        return {"id": cairn_id, "status": "compressed"}


def _json_or_none(value) -> str | None:
    """Convert a list/dict to JSON string for JSONB column, or None."""
    if value is None:
        return None
    import json
    return json.dumps(value)
