"""Primary ingestion strategy: LLM extracts key memories from sessions.

This is the strategy that tests Cairn's real-world pipeline — conversations
are processed by an LLM to extract discrete, searchable facts, which are
then stored with full enrichment.

Highest risk: extraction prompt quality is make-or-break for benchmark scores.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from cairn.core.utils import extract_json
from eval.benchmark.base import BenchmarkSession, IngestStrategy

if TYPE_CHECKING:
    from cairn.core.memory import MemoryStore
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM = """\
You are a memory extraction system. Given a conversation session, extract \
the key facts, preferences, events, and decisions that a personal assistant \
should remember for future reference.

Rules:
- Extract 5-15 discrete facts per session
- Each fact should be self-contained and searchable
- Include temporal context (dates, timeframes) when mentioned
- Capture preferences, opinions, plans, and commitments
- Capture relationships between people mentioned
- Do NOT extract small talk or filler
- Do NOT duplicate information across facts

Respond with a JSON array of objects:
[
  {"content": "the extracted fact", "importance": 0.5, "tags": ["tag1"]},
  ...
]

importance: 0.3 = trivial, 0.5 = normal, 0.7 = significant, 0.9 = critical
tags: 1-3 short descriptive tags per fact"""

EXTRACTION_USER = """\
Session date: {date}
Session ID: {session_id}

Conversation:
{conversation}

Extract the key facts from this conversation as a JSON array."""


class LLMExtractStrategy(IngestStrategy):
    """Extract memories from sessions via LLM, store with enrichment."""

    def __init__(self, llm: LLMInterface, max_turns_per_call: int = 50):
        self.llm = llm
        self.max_turns_per_call = max_turns_per_call

    @property
    def name(self) -> str:
        return "llm_extract"

    def ingest(
        self,
        sessions: list[BenchmarkSession],
        memory_store: MemoryStore,
        project: str,
    ) -> dict:
        start = time.time()
        total_memories = 0
        total_extracted = 0
        errors = 0

        for session in sessions:
            try:
                facts = self._extract_session(session)
                total_extracted += len(facts)

                for fact in facts:
                    memory_store.store(
                        content=fact["content"],
                        project=project,
                        memory_type="note",
                        importance=fact.get("importance", 0.5),
                        tags=fact.get("tags", []) + [f"session:{session.session_id}"],
                        session_name=session.session_id,
                        enrich=True,
                    )
                    total_memories += 1

                logger.debug(
                    "Session %s: extracted %d facts",
                    session.session_id,
                    len(facts),
                )
            except Exception:
                logger.exception("Extraction failed for session %s", session.session_id)
                errors += 1

        duration = time.time() - start
        logger.info(
            "LLMExtract: %d memories from %d sessions in %.1fs (%d errors)",
            total_memories,
            len(sessions),
            duration,
            errors,
        )
        return {
            "memory_count": total_memories,
            "extracted_facts": total_extracted,
            "sessions_processed": len(sessions),
            "errors": errors,
            "duration_s": round(duration, 2),
        }

    def _extract_session(self, session: BenchmarkSession) -> list[dict]:
        """Extract facts from a single session via LLM."""
        conversation = self._format_conversation(session)

        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": EXTRACTION_USER.format(
                    date=session.date or "unknown",
                    session_id=session.session_id,
                    conversation=conversation,
                ),
            },
        ]

        response = self.llm.generate(messages, max_tokens=2048)
        facts = extract_json(response, json_type="array")

        if not isinstance(facts, list):
            logger.warning(
                "Session %s: expected list, got %s", session.session_id, type(facts)
            )
            return []

        # Validate and clean
        valid = []
        for fact in facts:
            if isinstance(fact, dict) and fact.get("content"):
                # Prepend date if available
                content = fact["content"]
                if session.date and session.date not in content:
                    content = f"[{session.date}] {content}"
                    fact["content"] = content
                valid.append(fact)

        return valid

    def _format_conversation(self, session: BenchmarkSession) -> str:
        """Format session turns as a readable conversation string."""
        turns = session.turns[: self.max_turns_per_call]
        parts = []
        for turn in turns:
            role = turn.get("role", "user").capitalize()
            content = turn.get("content", "")
            parts.append(f"{role}: {content}")
        return "\n".join(parts)
