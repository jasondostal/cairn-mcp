"""Cairn lifecycle management. Set, stack, get, and compress episodic markers."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cairn.core.utils import get_or_create_project, get_project, extract_json

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

    def _claim_orphans(self, project_id: int, session_name: str) -> int:
        """Claim orphaned memories created during this session's time window.

        Memories stored via MCP without session_name (NULL) are matched by
        project and creation timestamp falling within the session's event
        window (from session_events). This avoids requiring agents to
        remember to pass session_name on every store() call.

        Returns:
            Number of orphaned memories claimed.
        """
        # Get the session's time bounds from shipped event batches
        bounds = self.db.execute_one(
            """
            SELECT MIN(created_at) AS first_event, MAX(created_at) AS last_event
            FROM session_events
            WHERE project_id = %s AND session_name = %s
            """,
            (project_id, session_name),
        )

        if not bounds or not bounds["first_event"]:
            return 0

        result = self.db.execute(
            """
            UPDATE memories
            SET session_name = %s
            WHERE project_id = %s
              AND session_name IS NULL
              AND is_active = true
              AND created_at >= %s
              AND created_at <= %s
            RETURNING id
            """,
            (session_name, project_id, bounds["first_event"], bounds["last_event"]),
        )

        claimed = len(result)
        if claimed > 0:
            logger.info(
                "Claimed %d orphaned memories for session %s (window: %s to %s)",
                claimed, session_name,
                bounds["first_event"].isoformat(),
                bounds["last_event"].isoformat(),
            )
        return claimed

    def _fetch_digests(self, project_id: int, session_name: str) -> list[dict]:
        """Query session_events for digested batches belonging to this session.

        Returns:
            List of dicts with batch_number, digest text. Only includes rows
            where digest is not NULL. Ordered by batch_number ASC.
        """
        return self.db.execute(
            """
            SELECT batch_number, digest
            FROM session_events
            WHERE project_id = %s AND session_name = %s AND digest IS NOT NULL
            ORDER BY batch_number ASC
            """,
            (project_id, session_name),
        )

    def set(self, project: str, session_name: str, events: list | None = None) -> dict:
        """Set a cairn at the end of a session.

        Fetches all stones with matching session_name, synthesizes a title
        and narrative, creates the cairn record, and links the stones.

        Pipeline v2: if digested event batches exist in session_events, uses them
        for narrative synthesis instead of raw events.

        Args:
            project: Project name.
            session_name: Session identifier (must match memories.session_name).
            events: Optional ordered event log (from hooks). Stored as JSONB.

        Returns:
            Dict with cairn details: id, title, narrative, memory_count, set_at.
        """
        from cairn.llm.prompts import build_cairn_narrative_messages, build_cairn_digest_narrative_messages

        project_id = get_or_create_project(self.db, project)

        # Check for existing cairn — upsert semantics allow both agent (MCP)
        # and hook (REST POST) to contribute to the same cairn without conflict.
        existing = self.db.execute_one(
            "SELECT id, events IS NOT NULL AS has_events, title, narrative, memory_count FROM cairns WHERE project_id = %s AND session_name = %s",
            (project_id, session_name),
        )
        if existing:
            return self._merge_existing(existing, project, project_id, session_name, events)

        # Reconcile orphaned memories — claim any that were stored without
        # session_name during this session's time window.
        self._claim_orphans(project_id, session_name)

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

        # Check for Pipeline v2 digests
        digests = self._fetch_digests(project_id, session_name)

        has_content = memory_count > 0 or (events and len(events) > 0) or len(digests) > 0

        # Skip empty sessions — no stones, no events, no digests, nothing to mark
        if not has_content:
            return {"skipped": True, "reason": "empty session", "session_name": session_name, "project": project}

        # Synthesize narrative via LLM (graceful degradation)
        title = None
        narrative = None
        can_synthesize = (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.session_synthesis
            and has_content
        )

        if can_synthesize:
            try:
                if digests:
                    # Pipeline v2: use pre-digested event summaries
                    messages = build_cairn_digest_narrative_messages(
                        stones, project, session_name, digests=digests,
                    )
                else:
                    # Pipeline v1 fallback: use raw events
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

        self._archive_events(session_name, events)
        self.db.commit()

        return {
            "id": cairn_id,
            "title": row["title"],
            "narrative": row["narrative"],
            "memory_count": row["memory_count"],
            "started_at": row["started_at"].isoformat() if hasattr(row["started_at"], "isoformat") else row["started_at"],
            "set_at": row["set_at"].isoformat() if hasattr(row["set_at"], "isoformat") else row["set_at"],
        }

    def _merge_existing(
        self, existing: dict, project: str, project_id: int,
        session_name: str, events: list | None,
    ) -> dict:
        """Handle upsert when a cairn already exists for this session.

        Three cases:
        1. Caller has events, existing has none → update with events + re-synthesize
        2. Caller has events, existing already has them → return existing (true idempotent)
        3. Caller has no events → return existing info (agent calling after hook)
        """
        from cairn.llm.prompts import build_cairn_narrative_messages, build_cairn_digest_narrative_messages

        cairn_id = existing["id"]
        has_existing_events = existing["has_events"]

        # Case 2 & 3: nothing new to contribute
        if not events or has_existing_events:
            return {
                "id": cairn_id,
                "title": existing["title"],
                "narrative": existing["narrative"],
                "memory_count": existing["memory_count"],
                "status": "already_exists",
            }

        # Case 1: caller brings events, existing cairn has none — merge them in
        # Reconcile orphans before re-fetching stones
        self._claim_orphans(project_id, session_name)

        # Re-fetch stones for narrative re-synthesis
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

        # Check for Pipeline v2 digests
        digests = self._fetch_digests(project_id, session_name)

        # Re-synthesize narrative with stones + events/digests
        title = None
        narrative = None
        can_synthesize = (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.session_synthesis
        )

        if can_synthesize:
            try:
                if digests:
                    messages = build_cairn_digest_narrative_messages(
                        stones, project, session_name, digests=digests,
                    )
                else:
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
                        narrative = raw.strip()
            except Exception:
                logger.warning("Cairn narrative re-synthesis failed during merge", exc_info=True)

        # Update the cairn row with events (and new narrative if synthesis succeeded)
        if title and narrative:
            self.db.execute(
                """
                UPDATE cairns SET events = %s::jsonb, title = %s, narrative = %s,
                       memory_count = %s
                WHERE id = %s
                """,
                (_json_or_none(events), title, narrative, memory_count, cairn_id),
            )
        else:
            # At minimum, attach the events even if synthesis failed
            self.db.execute(
                "UPDATE cairns SET events = %s::jsonb, memory_count = %s WHERE id = %s",
                (_json_or_none(events), memory_count, cairn_id),
            )

        self._archive_events(session_name, events)
        self.db.commit()

        # Re-read for response
        row = self.db.execute_one(
            "SELECT id, title, narrative, memory_count, started_at, set_at FROM cairns WHERE id = %s",
            (cairn_id,),
        )

        return {
            "id": row["id"],
            "title": row["title"],
            "narrative": row["narrative"],
            "memory_count": row["memory_count"],
            "started_at": row["started_at"].isoformat() if hasattr(row["started_at"], "isoformat") else row["started_at"],
            "set_at": row["set_at"].isoformat() if hasattr(row["set_at"], "isoformat") else row["set_at"],
            "status": "merged",
        }

    def _archive_events(self, session_name: str, events: list | None) -> None:
        """Write raw events to the file-based archive if configured."""
        if not events:
            return

        import json
        archive_dir = os.environ.get("CAIRN_EVENT_ARCHIVE_DIR")
        if not archive_dir:
            return

        try:
            os.makedirs(archive_dir, exist_ok=True)
            path = os.path.join(archive_dir, f"cairn-events-{session_name}.jsonl")
            with open(path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")
        except Exception:
            logger.warning("Failed to archive events to %s", archive_dir, exc_info=True)

    def stack(self, project: str | None = None, limit: int = 20) -> list[dict]:
        """View the trail — cairns for a project (or all projects), newest first.

        Args:
            project: Project name. None returns cairns across all projects.
            limit: Maximum cairns to return (default 20).

        Returns:
            List of cairn summaries ordered by set_at DESC.
        """
        if project is not None:
            project_id = get_project(self.db, project)
            if project_id is None:
                return []
            rows = self.db.execute(
                """
                SELECT c.id, c.session_name, c.title, c.narrative, c.memory_count,
                       c.started_at, c.set_at, c.is_compressed, p.name as project
                FROM cairns c
                LEFT JOIN projects p ON c.project_id = p.id
                WHERE c.project_id = %s AND c.set_at IS NOT NULL
                ORDER BY c.set_at DESC
                LIMIT %s
                """,
                (project_id, limit),
            )
        else:
            rows = self.db.execute(
                """
                SELECT c.id, c.session_name, c.title, c.narrative, c.memory_count,
                       c.started_at, c.set_at, c.is_compressed, p.name as project
                FROM cairns c
                LEFT JOIN projects p ON c.project_id = p.id
                WHERE c.set_at IS NOT NULL
                ORDER BY c.set_at DESC
                LIMIT %s
                """,
                (limit,),
            )

        return [
            {
                "id": r["id"],
                "session_name": r["session_name"],
                "title": r["title"],
                "narrative": r["narrative"],
                "memory_count": r["memory_count"],
                "project": r["project"],
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
