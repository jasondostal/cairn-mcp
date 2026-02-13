"""RAG pipeline for benchmark evaluation.

search Cairn -> format context -> LLM generates answer

Reuses SearchEngine (the thing being tested) and Cairn's
configured LLM for answer generation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from eval.benchmark.base import AnswerResult, BenchmarkQuestion
from eval.benchmark.judge import judge_answer

if TYPE_CHECKING:
    from cairn.core.search import SearchEngine
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

ANSWER_SYSTEM = """\
You are an intelligent memory assistant. Answer questions using ONLY the provided memories.

RULES:
1. Base your answer on the memories provided. You may combine facts from multiple memories.
2. Pay attention to WHO each memory is about. Names matter — if the question asks \
about Melanie but the memories only mention Caroline, say so.
3. If the question attributes something to the wrong person, correct the attribution. \
Example: Q "What is Melanie's favorite instrument?" but memories say Caroline plays guitar → \
Answer: "Caroline plays acoustic guitar, not Melanie."
4. If no memories mention the topic at all, say "I don't have information about that." \
But if memories mention related facts, use them — don't abstain just because the exact \
phrasing doesn't match.
5. If memories contain contradictory information, prefer the most recent.
6. For time references ("last year", "two months ago"), calculate the actual date from \
the memory timestamp. Example: memory from May 2022 says "went to India last year" → 2021.
7. Always convert relative time references to specific dates/months/years.
8. Keep your answer concise — under 10 words when possible.

APPROACH:
1. Identify which memories relate to the question.
2. Check if the PERSON in the question matches the person in the memories.
3. Check timestamps for temporal questions — show your calculation.
4. Give a specific, evidence-based answer."""

ANSWER_USER = """\
Memories:
{context}

Question: {question}

Answer:"""


def format_context(memories: list[dict], max_chars: int = 10000) -> str:
    """Format retrieved memories as numbered context, grouped by session."""
    # Group by session tag
    from collections import OrderedDict

    sessions: OrderedDict[str, list[dict]] = OrderedDict()
    for mem in memories:
        session = "unknown"
        for tag in mem.get("tags", []):
            if tag.startswith("session:"):
                session = tag[8:]  # strip "session:" prefix
                break
        sessions.setdefault(session, []).append(mem)

    parts = []
    total = 0
    i = 0
    for session_id, mems in sessions.items():
        header = f"--- Session: {session_id} ---"
        if total + len(header) > max_chars:
            break
        parts.append(header)
        total += len(header)

        for mem in mems:
            i += 1
            content = mem.get("content", "")
            entry = f"[{i}] {content}"
            if total + len(entry) > max_chars:
                break
            parts.append(entry)
            total += len(entry)

    return "\n".join(parts)



def evaluate_question(
    question: BenchmarkQuestion,
    search_engine: SearchEngine,
    llm: LLMInterface,
    judge_llm: LLMInterface | None,
    project: str,
    search_limit: int = 10,
    extra_search_kwargs: dict | None = None,
) -> AnswerResult:
    """Run the full RAG pipeline for a single question.

    1. Search Cairn for relevant memories
    2. Format context
    3. Generate answer via LLM
    4. Score with judge (if judge_llm provided)

    Returns:
        AnswerResult with generated answer and optional judge score.
    """
    # 1. Search
    search_kwargs = {
        "query": question.question,
        "project": project,
        "limit": search_limit,
        "include_full": True,
    }
    if extra_search_kwargs:
        search_kwargs.update(extra_search_kwargs)

    try:
        memories = search_engine.search(**search_kwargs)
    except Exception:
        logger.exception("Search failed for question %s", question.id)
        memories = []

    # 2. Format context (grouped by session for multi-hop reasoning)
    context = format_context(memories)

    # 3. Generate answer
    if not context.strip():
        generated = "No relevant memories found."
    else:
        messages = [
            {"role": "system", "content": ANSWER_SYSTEM},
            {
                "role": "user",
                "content": ANSWER_USER.format(
                    context=context, question=question.question
                ),
            },
        ]
        try:
            generated = llm.generate(messages, max_tokens=256)
        except Exception:
            logger.exception("Answer generation failed for question %s", question.id)
            generated = "Error generating answer."

    # 4. Judge
    score = None
    reasoning = ""
    if judge_llm is not None:
        is_abstention = question.question_type == "abstention" or question.metadata.get(
            "has_answer"
        ) is False
        score, reasoning = judge_answer(
            judge_llm,
            question.question,
            question.expected_answer,
            generated,
            is_abstention=is_abstention,
        )

    return AnswerResult(
        question_id=question.id,
        question_type=question.question_type,
        expected_answer=question.expected_answer,
        generated_answer=generated,
        retrieved_memories=[
            {"id": m.get("id"), "content": m.get("content", "")[:200]}
            for m in memories
        ],
        judge_score=score,
        judge_reasoning=reasoning,
    )
