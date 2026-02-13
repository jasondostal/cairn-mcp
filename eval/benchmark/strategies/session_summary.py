"""Comparison ingestion strategy: one LLM summary per session.

Tests whether a single dense summary per session is sufficient
for retrieval, or whether discrete extracted facts perform better.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from eval.benchmark.base import BenchmarkSession, IngestStrategy

if TYPE_CHECKING:
    from cairn.core.memory import MemoryStore
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM = """\
You are a conversation summarizer. Given a conversation session, produce a \
comprehensive summary that captures all key facts, preferences, events, \
decisions, and relationships mentioned.

The summary should be detailed enough that someone could answer specific \
questions about the conversation based solely on your summary.

Include:
- All names, dates, and specific details mentioned
- Preferences and opinions expressed
- Plans, commitments, and decisions made
- Relationships between people
- Any changes to previously known information"""

SUMMARY_USER = """\
Session date: {date}
Session ID: {session_id}

Conversation:
{conversation}

Provide a comprehensive summary of this conversation."""


class SessionSummaryStrategy(IngestStrategy):
    """Store one LLM-generated summary per session."""

    def __init__(self, llm: LLMInterface, max_turns_per_call: int = 50):
        self.llm = llm
        self.max_turns_per_call = max_turns_per_call

    @property
    def name(self) -> str:
        return "session_summary"

    def ingest(
        self,
        sessions: list[BenchmarkSession],
        memory_store: MemoryStore,
        project: str,
    ) -> dict:
        start = time.time()
        count = 0
        errors = 0

        for session in sessions:
            try:
                summary = self._summarize_session(session)
                if summary.strip():
                    memory_store.store(
                        content=summary,
                        project=project,
                        memory_type="note",
                        importance=0.7,
                        tags=[f"session:{session.session_id}", "session-summary"],
                        session_name=session.session_id,
                        enrich=True,
                    )
                    count += 1
                    logger.debug("Session %s: stored summary", session.session_id)
            except Exception:
                logger.exception("Summary failed for session %s", session.session_id)
                errors += 1

        duration = time.time() - start
        logger.info(
            "SessionSummary: %d summaries from %d sessions in %.1fs (%d errors)",
            count,
            len(sessions),
            duration,
            errors,
        )
        return {
            "memory_count": count,
            "sessions_processed": len(sessions),
            "errors": errors,
            "duration_s": round(duration, 2),
        }

    def _summarize_session(self, session: BenchmarkSession) -> str:
        """Generate a summary for a single session."""
        turns = session.turns[: self.max_turns_per_call]
        parts = []
        for turn in turns:
            role = turn.get("role", "user").capitalize()
            content = turn.get("content", "")
            parts.append(f"{role}: {content}")
        conversation = "\n".join(parts)

        messages = [
            {"role": "system", "content": SUMMARY_SYSTEM},
            {
                "role": "user",
                "content": SUMMARY_USER.format(
                    date=session.date or "unknown",
                    session_id=session.session_id,
                    conversation=conversation,
                ),
            },
        ]

        return self.llm.generate(messages, max_tokens=1024)
