"""Session summary synthesis. Fetches all memories for a session and synthesizes a narrative."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.config import LLMCapabilities
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)


class SessionSynthesizer:
    """Synthesize session memories into a coherent narrative."""

    def __init__(
        self, db: Database, *,
        llm: LLMInterface | None = None,
        capabilities: LLMCapabilities | None = None,
    ):
        self.db = db
        self.llm = llm
        self.capabilities = capabilities

    def synthesize(self, project: str, session_name: str) -> dict:
        """Synthesize all memories for a session into a narrative.

        Returns:
            Dict with session_name, project, memory_count, and either
            'narrative' (LLM) or 'memories' (fallback list).
        """
        from cairn.llm.prompts import build_session_synthesis_messages

        # Fetch memories for this session
        rows = self.db.execute(
            """
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.created_at
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE p.name = %s AND m.session_name = %s AND m.is_active = true
            ORDER BY m.created_at ASC
            """,
            (project, session_name),
        )

        if not rows:
            return {
                "session_name": session_name,
                "project": project,
                "memory_count": 0,
                "narrative": None,
                "memories": [],
            }

        # Build fallback: structured list of memory summaries
        memory_summaries = [
            {
                "id": r["id"],
                "summary": r.get("summary") or r["content"][:200],
                "memory_type": r["memory_type"],
                "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else r["created_at"],
            }
            for r in rows
        ]

        # Try LLM synthesis
        can_synthesize = (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.session_synthesis
        )

        if can_synthesize:
            try:
                messages = build_session_synthesis_messages(rows, project, session_name)
                narrative = self.llm.generate(messages, max_tokens=1024)
                if narrative and narrative.strip():
                    return {
                        "session_name": session_name,
                        "project": project,
                        "memory_count": len(rows),
                        "narrative": narrative.strip(),
                        "memories": memory_summaries,
                    }
            except Exception:
                logger.warning("Session synthesis LLM call failed, returning fallback", exc_info=True)

        # Fallback: no narrative, just structured data
        return {
            "session_name": session_name,
            "project": project,
            "memory_count": len(rows),
            "narrative": None,
            "memories": memory_summaries,
        }
