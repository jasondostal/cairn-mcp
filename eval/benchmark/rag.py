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
You are an intelligent memory assistant tasked with retrieving accurate \
information from conversation memories.

INSTRUCTIONS:
1. Carefully analyze all provided memories.
2. Pay special attention to timestamps to determine the answer.
3. If the question asks about a specific event or fact, look for direct evidence in the memories.
4. If memories contain contradictory information, prioritize the most recent memory.
5. If there is a question about time references (like "last year", "two months ago"), \
calculate the actual date based on the memory timestamp. For example, if a memory from \
4 May 2022 mentions "went to India last year," then the trip occurred in 2021.
6. Always convert relative time references to specific dates, months, or years.
7. The answer should be less than 5-6 words.

APPROACH (Think step by step):
1. Examine all memories that contain information related to the question.
2. Look for explicit mentions of dates, times, locations, or events that answer the question.
3. If the answer requires calculation (e.g., converting relative time references), show your work.
4. Formulate a precise, concise answer based solely on the evidence in the memories.
5. Double-check that your answer directly addresses the question asked.
6. Ensure your final answer is specific and avoids vague time references."""

ANSWER_USER = """\
Memories:
{context}

Question: {question}

Answer:"""


def format_context(memories: list[dict], max_chars: int = 8000) -> str:
    """Format retrieved memories as numbered context string."""
    parts = []
    total = 0
    for i, mem in enumerate(memories, 1):
        content = mem.get("content", "")
        entry = f"[{i}] {content}"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n".join(parts)


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

    # 2. Format context
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
            generated = llm.generate(messages, max_tokens=150)
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
