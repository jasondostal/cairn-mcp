"""Episodic ingestion: raw turns + two-pass extracted facts.

Combines two layers for maximum recall and precision:
  - Layer 1 (raw turns): Every conversation turn stored as an individual
    memory with enrich=False. Embedding-only cost. Provides 100% content
    coverage as a recall safety net for vector search.
  - Layer 2 (extracted facts): Two-pass normalization + extraction pipeline
    produces 20-50 structured facts per session. These carry tags, entities,
    importance, and aspect classification for precision retrieval.

Both layers are tagged with session_id and a layer tag (layer:raw or
layer:extracted) so they correlate during search and can be analyzed
independently during failure analysis.

Cost: ~3000 raw turn embeddings + ~200 LLM calls (2 per session).
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from eval.benchmark.base import BenchmarkSession, IngestStrategy
from eval.benchmark.runner_bench import event
from eval.benchmark.strategies.two_pass import TwoPassStrategy

if TYPE_CHECKING:
    from cairn.core.memory import MemoryStore
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)


class EpisodicStrategy(IngestStrategy):
    """Raw turns + two-pass extracted facts for maximum coverage."""

    def __init__(self, llm: LLMInterface, max_turns_per_call: int = 50):
        self.llm = llm
        self._two_pass = TwoPassStrategy(llm, max_turns_per_call=max_turns_per_call)

    @property
    def name(self) -> str:
        return "episodic"

    def ingest(
        self,
        sessions: list[BenchmarkSession],
        memory_store: MemoryStore,
        project: str,
        workers: int = 16,
    ) -> dict:
        start = time.time()
        raw_count = 0
        extracted_count = 0
        errors = 0
        total_sessions = len(sessions)
        counter_lock = threading.Lock()
        done = {"n": 0}

        def _process_one(session: BenchmarkSession) -> tuple[int, int, int]:
            """Process a single session. Returns (raw, extracted, errors)."""
            s_raw = self._store_raw_turns(session, memory_store, project)
            s_extracted = 0
            s_errors = 0

            try:
                facts = self._two_pass._process_session(session)
                for fact in facts:
                    content = fact["content"]
                    if session.date and session.date not in content:
                        content = f"[{session.date}] {content}"

                    memory_store.store(
                        content=content,
                        project=project,
                        memory_type="note",
                        importance=fact.get("importance", 0.5),
                        tags=fact.get("tags", [])
                        + [f"session:{session.session_id}", "layer:extracted"],
                        session_name=session.session_id,
                        enrich=False,
                    )
                    s_extracted += 1

                logger.debug(
                    "Session %s: %d raw + %d extracted",
                    session.session_id,
                    len(session.turns),
                    len(facts),
                )
            except Exception:
                logger.exception(
                    "Extraction failed for session %s (raw turns preserved)",
                    session.session_id,
                )
                s_errors = 1

            with counter_lock:
                done["n"] += 1
                n = done["n"]
                if n % 10 == 0 or n == total_sessions:
                    elapsed = time.time() - start
                    rate = n / elapsed if elapsed > 0 else 0
                    eta = (total_sessions - n) / rate if rate > 0 else 0
                    event("ingest_progress", f"[{n}/{total_sessions}] {rate:.1f} sess/s ETA {eta:.0f}s")

            return s_raw, s_extracted, s_errors

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_one, s): s for s in sessions}
            for future in as_completed(futures):
                s_raw, s_extracted, s_errors = future.result()
                raw_count += s_raw
                extracted_count += s_extracted
                errors += s_errors

        duration = time.time() - start
        total = raw_count + extracted_count
        logger.info(
            "Episodic: %d total memories (%d raw + %d extracted) "
            "from %d sessions in %.1fs (%d errors, %d workers)",
            total,
            raw_count,
            extracted_count,
            len(sessions),
            duration,
            errors,
            workers,
        )
        return {
            "memory_count": total,
            "raw_count": raw_count,
            "extracted_count": extracted_count,
            "sessions_processed": len(sessions),
            "errors": errors,
            "duration_s": round(duration, 2),
        }

    def _store_raw_turns(
        self,
        session: BenchmarkSession,
        memory_store: MemoryStore,
        project: str,
    ) -> int:
        """Store each turn as an individual memory. Returns count stored."""
        count = 0
        for turn in session.turns:
            content = turn.get("content", "")
            if not content.strip():
                continue

            role = turn.get("role", "user")
            speaker = turn.get("speaker", role)
            date_prefix = f"[{session.date}] " if session.date else ""
            tagged = f"{date_prefix}{speaker}: {content}"

            memory_store.store(
                content=tagged,
                project=project,
                memory_type="note",
                importance=0.5,
                tags=[
                    f"session:{session.session_id}",
                    f"role:{role}",
                    "layer:raw",
                ],
                session_name=session.session_id,
                enrich=False,
            )
            count += 1
        return count
