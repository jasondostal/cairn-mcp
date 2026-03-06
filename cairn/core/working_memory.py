"""Persistent working memory — active cognitive workspace.

Stores pre-crystallized cognitive items (hypotheses, questions, tensions,
connections, threads, intuitions) that persist across sessions. Items have
salience scores that decay over time and can be boosted through engagement.

Working memory is the upstream of memories, beliefs, and work items —
the pre-decisional cognitive state that gives agents continuity of thought.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cairn.core.analytics import track_operation
from cairn.core.constants import (
    VALID_WM_RESOLUTION_TYPES,
    VALID_WM_TYPES,
    WM_DEFAULT_SALIENCE,
    WM_SALIENCE_BOOST_FLOOR,
    WM_SALIENCE_DECAY_RATE,
)
from cairn.core.utils import get_or_create_project, get_project

if TYPE_CHECKING:
    from cairn.core.beliefs import BeliefStore
    from cairn.core.event_bus import EventBus
    from cairn.core.memory import MemoryStore
    from cairn.embedding.interface import EmbeddingInterface
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class WorkingMemoryStore:
    """Manages persistent working memory items.

    Items have salience that decays over time (computed at read time,
    not via background worker). Pinned items skip decay. Engaging with
    an item (boost) resets the decay clock.
    """

    # Mapping from working memory item_type to memory_type for graduation
    _GRADUATION_TYPE_MAP = {
        "hypothesis": "learning",
        "question": "note",
        "tension": "decision",
        "connection": "note",
        "thread": "progress",
        "intuition": "learning",
    }

    def __init__(
        self,
        db: Database,
        embedding: EmbeddingInterface | None = None,
        event_bus: EventBus | None = None,
        memory_store: MemoryStore | None = None,
        belief_store: BeliefStore | None = None,
    ) -> None:
        self.db = db
        self.embedding = embedding
        self.event_bus = event_bus
        self.memory_store = memory_store
        self.belief_store = belief_store

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    @track_operation("working_memory.capture")
    def capture(
        self,
        project: str,
        content: str,
        *,
        item_type: str = "thread",
        salience: float | None = None,
        author: str | None = None,
        session_name: str | None = None,
    ) -> dict:
        """Store a new working memory item.

        Args:
            project: Project name.
            content: The cognitive item content.
            item_type: One of VALID_WM_TYPES.
            salience: Override initial salience. Auto-set by type if omitted.
            author: Who is thinking this (e.g. "human", "assistant", agent name).
            session_name: Session that created this item.
        """
        if item_type not in VALID_WM_TYPES:
            return {"error": f"Invalid item_type '{item_type}'. Must be one of: {VALID_WM_TYPES}"}

        if salience is None:
            salience = WM_DEFAULT_SALIENCE.get(item_type, 0.6)
        salience = max(0.0, min(1.0, salience))

        project_id = get_or_create_project(self.db, project)

        # Embed for semantic similarity
        embedding_vec = None
        if self.embedding:
            try:
                embedding_vec = self.embedding.embed(content)
            except Exception:
                logger.warning("Failed to embed working memory item", exc_info=True)

        row = self.db.execute_one(
            """
            INSERT INTO working_memory
                (project_id, content, item_type, salience, author,
                 embedding, session_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (project_id, content, item_type, salience, author,
             embedding_vec, session_name),
        )
        assert row is not None
        self.db.commit()

        item_id = row["id"]
        logger.info(
            "Captured working memory #%d (%s, salience=%.2f, project=%s)",
            item_id, item_type, salience, project,
        )

        self._publish("working_memory.captured", project_id,
                       item_id=item_id, item_type=item_type, author=author)

        return {
            "id": item_id,
            "project": project,
            "item_type": item_type,
            "salience": salience,
            "content": content,
            "author": author,
            "pinned": False,
            "status": "active",
            "created_at": row["created_at"].isoformat(),
        }

    @track_operation("working_memory.list")
    def list_active(
        self,
        project: str | list[str],
        *,
        author: str | None = None,
        item_type: str | None = None,
        min_salience: float = 0.0,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """List active working memory items sorted by computed salience."""
        if isinstance(project, list):
            conditions = ["p.name = ANY(%s)", "wm.status = 'active'"]
            params: list = [project]
        else:
            project_id = get_project(self.db, project)
            if project_id is None:
                return {"items": [], "total": 0}
            conditions = ["wm.project_id = %s", "wm.status = 'active'"]
            params = [project_id]

        if author:
            conditions.append("wm.author = %s")
            params.append(author)
        if item_type:
            conditions.append("wm.item_type = %s")
            params.append(item_type)

        where = " AND ".join(conditions)

        # Count total
        count_join = " LEFT JOIN projects p ON wm.project_id = p.id" if isinstance(project, list) else ""
        count_row = self.db.execute_one(
            f"SELECT count(*) as cnt FROM working_memory wm{count_join} WHERE {where}",
            tuple(params),
        )
        total = count_row["cnt"] if count_row else 0

        # Fetch items
        rows = self.db.execute(
            f"""
            SELECT wm.id, wm.content, wm.item_type, wm.salience, wm.author,
                   wm.pinned, wm.status, wm.session_name,
                   wm.resolved_into, wm.resolution_id, wm.resolution_note,
                   wm.created_at, wm.updated_at,
                   p.name as project
            FROM working_memory wm
            LEFT JOIN projects p ON wm.project_id = p.id
            WHERE {where}
            ORDER BY wm.salience DESC, wm.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params) + (limit, offset),
        )

        items = []
        for r in rows:
            computed = self._compute_salience(
                float(r["salience"]), r["updated_at"], r["pinned"],
            )
            if computed < min_salience:
                continue
            items.append(self._row_to_dict(r, computed_salience=computed))

        return {"items": items, "total": total}

    @track_operation("working_memory.get")
    def get(self, item_id: int) -> dict:
        """Get full detail for a working memory item."""
        row = self.db.execute_one(
            """
            SELECT wm.id, wm.content, wm.item_type, wm.salience, wm.author,
                   wm.pinned, wm.status, wm.session_name,
                   wm.resolved_into, wm.resolution_id, wm.resolution_note,
                   wm.created_at, wm.updated_at, wm.archived_at,
                   p.name as project
            FROM working_memory wm
            LEFT JOIN projects p ON wm.project_id = p.id
            WHERE wm.id = %s
            """,
            (item_id,),
        )
        if not row:
            return {"error": f"Working memory item {item_id} not found"}

        computed = self._compute_salience(
            float(row["salience"]), row["updated_at"], row["pinned"],
        )
        return self._row_to_dict(row, computed_salience=computed)

    @track_operation("working_memory.resolve")
    def resolve(
        self,
        item_id: int,
        *,
        resolved_into: str,
        resolution_id: str | None = None,
        resolution_note: str | None = None,
    ) -> dict:
        """Mark a working memory item as resolved into a concrete entity.

        When resolved_into is "memory" or "belief" and no resolution_id is
        provided, auto-creates the target entity (graduation).
        """
        if resolved_into not in VALID_WM_RESOLUTION_TYPES:
            return {"error": f"Invalid resolved_into '{resolved_into}'. Must be one of: {VALID_WM_RESOLUTION_TYPES}"}

        # Fetch item before updating (need content + project for graduation)
        item = self.db.execute_one(
            """
            SELECT wm.id, wm.content, wm.item_type, wm.project_id, wm.author,
                   p.name as project
            FROM working_memory wm
            LEFT JOIN projects p ON wm.project_id = p.id
            WHERE wm.id = %s AND wm.status = 'active'
            """,
            (item_id,),
        )
        if not item:
            return {"error": f"Working memory item {item_id} not found or not active"}

        # Graduate: auto-create target entity if no explicit resolution_id
        if resolution_id is None:
            graduated_id = self._graduate(item, resolved_into, resolution_note)
            if graduated_id is not None:
                resolution_id = str(graduated_id)

        row = self.db.execute_one(
            """
            UPDATE working_memory
            SET status = 'resolved', resolved_into = %s,
                resolution_id = %s, resolution_note = %s,
                updated_at = NOW()
            WHERE id = %s AND status = 'active'
            RETURNING id, project_id
            """,
            (resolved_into, resolution_id, resolution_note, item_id),
        )
        if not row:
            return {"error": f"Working memory item {item_id} not found or not active"}
        self.db.commit()

        logger.info("Resolved working memory #%d → %s (id=%s)",
                     item_id, resolved_into, resolution_id)

        self._publish("working_memory.resolved", row["project_id"],
                       item_id=item_id, resolved_into=resolved_into,
                       resolution_id=resolution_id)

        if resolution_id and resolved_into in ("memory", "belief"):
            self._publish("working_memory.graduated", row["project_id"],
                           item_id=item_id, resolved_into=resolved_into,
                           entity_id=resolution_id)

        return self.get(item_id)

    def _graduate(
        self, item: dict, resolved_into: str, note: str | None,
    ) -> int | None:
        """Auto-create the target entity for graduation. Returns entity ID or None."""
        project = item.get("project")
        content = item["content"]

        if resolved_into == "memory" and self.memory_store and project:
            memory_type = self._GRADUATION_TYPE_MAP.get(item["item_type"], "note")
            try:
                result = self.memory_store.store(
                    content=content,
                    project=project,
                    memory_type=memory_type,
                    importance=0.6,
                    tags=["graduated"],
                    author=item.get("author"),
                    enrich=False,
                )
                return result.get("id")
            except Exception:
                logger.warning("Failed to graduate WM #%d → memory", item["id"], exc_info=True)
                return None

        if resolved_into == "belief" and self.belief_store and project:
            try:
                result = self.belief_store.crystallize(
                    project=project,
                    content=content,
                    confidence=0.7,
                    agent_name=item.get("author"),
                    provenance="crystallized",
                )
                return result.get("id")
            except Exception:
                logger.warning("Failed to graduate WM #%d → belief", item["id"], exc_info=True)
                return None

        return None

    @track_operation("working_memory.pin")
    def pin(self, item_id: int) -> dict:
        """Pin an item to prevent salience decay."""
        row = self.db.execute_one(
            """
            UPDATE working_memory
            SET pinned = TRUE, updated_at = NOW()
            WHERE id = %s AND status = 'active'
            RETURNING id
            """,
            (item_id,),
        )
        if not row:
            return {"error": f"Working memory item {item_id} not found or not active"}
        self.db.commit()
        return self.get(item_id)

    @track_operation("working_memory.unpin")
    def unpin(self, item_id: int) -> dict:
        """Unpin an item, resuming salience decay from current level."""
        # First get current state to compute decayed salience
        current = self.db.execute_one(
            "SELECT salience, updated_at, pinned FROM working_memory WHERE id = %s",
            (item_id,),
        )
        if not current:
            return {"error": f"Working memory item {item_id} not found"}

        # Write the computed (decayed) salience as the new base,
        # so decay starts from the realistic current value
        computed = self._compute_salience(
            float(current["salience"]), current["updated_at"], current["pinned"],
        )

        self.db.execute(
            """
            UPDATE working_memory
            SET pinned = FALSE, salience = %s, updated_at = NOW()
            WHERE id = %s AND status = 'active'
            """,
            (computed, item_id),
        )
        self.db.commit()
        return self.get(item_id)

    @track_operation("working_memory.boost")
    def boost(self, item_id: int) -> dict:
        """Boost an item's salience (engaged with it). Resets decay clock."""
        current = self.db.execute_one(
            "SELECT salience, updated_at, pinned, project_id FROM working_memory WHERE id = %s AND status = 'active'",
            (item_id,),
        )
        if not current:
            return {"error": f"Working memory item {item_id} not found or not active"}

        computed = self._compute_salience(
            float(current["salience"]), current["updated_at"], current["pinned"],
        )
        new_salience = max(computed, WM_SALIENCE_BOOST_FLOOR)

        self.db.execute(
            """
            UPDATE working_memory
            SET salience = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (new_salience, item_id),
        )
        self.db.commit()

        self._publish("working_memory.boosted", current["project_id"],
                       item_id=item_id, salience=new_salience)

        return self.get(item_id)

    @track_operation("working_memory.archive")
    def archive(self, item_id: int) -> dict:
        """Manually archive a working memory item."""
        row = self.db.execute_one(
            """
            UPDATE working_memory
            SET status = 'archived', archived_at = NOW(), updated_at = NOW()
            WHERE id = %s AND status = 'active'
            RETURNING id, project_id
            """,
            (item_id,),
        )
        if not row:
            return {"error": f"Working memory item {item_id} not found or not active"}
        self.db.commit()

        self._publish("working_memory.archived", row["project_id"],
                       item_id=item_id)

        return {"id": item_id, "status": "archived"}

    # ------------------------------------------------------------------
    # Orient integration
    # ------------------------------------------------------------------

    def orient_items(self, project: str, *, limit: int = 5) -> list[dict]:
        """Return top active items for orient() injection.

        Compact format, sorted by computed salience (highest first).
        """
        project_id = get_project(self.db, project)
        if project_id is None:
            return []

        rows = self.db.execute(
            """
            SELECT id, content, item_type, salience, author, pinned,
                   updated_at, created_at
            FROM working_memory
            WHERE project_id = %s AND status = 'active'
            ORDER BY salience DESC, created_at DESC
            LIMIT %s
            """,
            (project_id, limit * 2),  # fetch extra to account for post-decay filtering
        )

        items = []
        for r in rows:
            computed = self._compute_salience(
                float(r["salience"]), r["updated_at"], r["pinned"],
            )
            if computed < 0.05:  # skip nearly-faded items
                continue
            items.append({
                "id": r["id"],
                "item_type": r["item_type"],
                "content": r["content"],
                "salience": round(computed, 3),
                "author": r["author"],
                "pinned": r["pinned"],
            })
            if len(items) >= limit:
                break

        return items

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_salience(
        base_salience: float,
        updated_at: datetime,
        pinned: bool,
    ) -> float:
        """Compute current salience with time-based decay.

        Decay formula: base × (0.97 ^ days_elapsed)
        Pinned items skip decay entirely.
        """
        if pinned:
            return base_salience

        now = datetime.now(UTC)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)

        elapsed = (now - updated_at).total_seconds() / 86400.0  # days
        if elapsed <= 0:
            return base_salience

        decayed = base_salience * math.pow(WM_SALIENCE_DECAY_RATE, elapsed)
        return max(0.0, min(1.0, decayed))

    @staticmethod
    def _row_to_dict(row: dict, *, computed_salience: float | None = None) -> dict:
        """Convert a database row to a response dict."""
        result = {
            "id": row["id"],
            "project": row.get("project"),
            "content": row["content"],
            "item_type": row["item_type"],
            "salience": round(computed_salience, 3) if computed_salience is not None else float(row["salience"]),
            "base_salience": float(row["salience"]),
            "author": row.get("author"),
            "pinned": row["pinned"],
            "status": row["status"],
            "session_name": row.get("session_name"),
            "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
            "updated_at": row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
        }
        if row.get("resolved_into"):
            result["resolved_into"] = row["resolved_into"]
            result["resolution_id"] = row.get("resolution_id")
            result["resolution_note"] = row.get("resolution_note")
        if row.get("archived_at"):
            result["archived_at"] = row["archived_at"].isoformat() if hasattr(row["archived_at"], "isoformat") else str(row["archived_at"])
        return result

    def _publish(self, event_type: str, project_id: int | None = None, **payload) -> None:
        """Publish an event to the event bus."""
        if not self.event_bus:
            return
        project_name = None
        if project_id:
            row = self.db.execute_one(
                "SELECT name FROM projects WHERE id = %s", (project_id,),
            )
            if row:
                project_name = row["name"]
        try:
            self.event_bus.publish(
                session_name="",
                event_type=event_type,
                project=project_name,
                payload=payload if payload else None,
            )
        except Exception:
            logger.warning("Failed to publish %s", event_type, exc_info=True)
