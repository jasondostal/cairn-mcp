"""Baseline ingestion strategy: store each conversation turn as a memory.

No LLM extraction, no enrichment. Provides a lower bound for
comparison — if Cairn can't beat raw-turn retrieval, the extraction
pipeline has a problem.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from eval.benchmark.base import BenchmarkSession, IngestStrategy

if TYPE_CHECKING:
    from cairn.core.memory import MemoryStore

logger = logging.getLogger(__name__)


class RawTurnsStrategy(IngestStrategy):
    """Store each conversation turn as an individual memory."""

    @property
    def name(self) -> str:
        return "raw_turns"

    def ingest(
        self,
        sessions: list[BenchmarkSession],
        memory_store: MemoryStore,
        project: str,
    ) -> dict:
        start = time.time()
        count = 0

        for session in sessions:
            for i, turn in enumerate(session.turns):
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if not content.strip():
                    continue

                # Prefix with role and session date for context
                date_prefix = f"[{session.date}] " if session.date else ""
                tagged_content = f"{date_prefix}{role}: {content}"

                memory_store.store(
                    content=tagged_content,
                    project=project,
                    memory_type="note",
                    importance=0.5,
                    tags=[f"session:{session.session_id}", f"role:{role}"],
                    session_name=session.session_id,
                    enrich=False,  # Skip LLM enrichment for baseline
                )
                count += 1

            logger.debug(
                "Session %s: stored %d turns", session.session_id, len(session.turns)
            )

        duration = time.time() - start
        logger.info("RawTurns: stored %d memories in %.1fs", count, duration)
        return {"memory_count": count, "duration_s": round(duration, 2)}
