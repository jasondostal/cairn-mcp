"""RAG pipeline for benchmark evaluation.

search Cairn -> format context -> LLM generates answer

Reuses SearchEngine (the thing being tested) and Cairn's
configured LLM for answer generation.

Supports two scoring modes:
- LLM judge (default): generates answer via LLM, scores with LLM-as-judge
- Retrieval (cheap): checks if retrieved memories contain the expected answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from eval.benchmark.base import AnswerResult, BenchmarkQuestion
from eval.benchmark.judge import judge_answer
from eval.benchmark.qa_metrics import compute_f1

if TYPE_CHECKING:
    from cairn.core.search import SearchEngine
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

ANSWER_SYSTEM = """\
You are an intelligent memory assistant tasked with retrieving accurate information \
from conversation memories.

CRITICAL REQUIREMENTS:
1. NEVER omit specific names — use "Amy's colleague Rob" not "a colleague."
2. ALWAYS include exact numbers, amounts, prices, percentages, dates, times.
3. PRESERVE frequencies exactly — "every Tuesday and Thursday" not "twice a week."
4. MAINTAIN all proper nouns and entities as they appear.
5. If memories contain contradictory information, prefer the most recent timestamp.
6. If the question attributes something to the wrong person, correct the attribution.
7. If no memories mention the topic at all, say "I don't have information about that." \
But if memories mention related facts, use them.

RESPONSE FORMAT — follow this Chain-of-Thought process:

## STEP 1: RELEVANT MEMORIES
List each memory that relates to the question, with its timestamp.

## STEP 2: KEY DETAILS
Extract ALL specific details: names, numbers, dates, times, frequencies, locations, entities.

## STEP 3: CROSS-MEMORY LINKING
Identify entities that appear across multiple memories. Make reasonable inferences \
when entities are strongly connected. E.g. "Memory 1 says A moved from hometown, \
Memory 2 says A's hometown is LA → A moved from LA."

## STEP 4: TIME CALCULATION
Convert relative time references to specific dates. E.g. memory from May 2022 says \
"went to India last year" → trip was in 2021.

## STEP 5: CONTRADICTION CHECK
If multiple memories conflict, note which is most recent and resolve.

## STEP 6: DETAIL VERIFICATION
Verify all person names, locations, numbers, frequencies, dates, and proper nouns \
are preserved in your answer.

## STEP 7: FINAL ANSWER
Provide a concise answer (under 10 words when possible) with ALL specific details preserved."""

ANSWER_USER = """\
Memories:
{context}

Question: {question}

Answer:"""


def format_context(memories: list[dict], max_chars: int = 10000) -> str:
    """Format retrieved memories with timestamps, grouped by session."""
    import re
    from collections import OrderedDict

    # Extract timestamp from content like "[1:56 pm on 8 May, 2023]"
    ts_pattern = re.compile(r"\[([^\]]*\d{4}[^\]]*)\]\s*")

    sessions: OrderedDict[str, list[dict]] = OrderedDict()
    for mem in memories:
        session = "unknown"
        for tag in mem.get("tags", []):
            if tag.startswith("session:"):
                session = tag[8:]
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
            # Extract and reformat timestamp for prominence
            ts_match = ts_pattern.match(content)
            if ts_match:
                timestamp = ts_match.group(1)
                body = content[ts_match.end():]
                entry = f"[{i}] [{timestamp}] {body}"
            else:
                entry = f"[{i}] {content}"
            if total + len(entry) > max_chars:
                break
            parts.append(entry)
            total += len(entry)

    return "\n".join(parts)



def _extract_final_answer(generated: str) -> str:
    """Extract the final answer from a CoT response.

    Looks for '## FINAL ANSWER', '## STEP 7', or similar markers.
    Falls back to the full text if no marker found.
    """
    import re

    # Try common CoT end markers
    for pattern in [
        r"##\s*FINAL\s*ANSWER[:\s]*\n?(.*)",
        r"##\s*STEP\s*7[:\s]*.*?\n(.*)",
        r"\*\*FINAL\s*ANSWER[:\s]*\*\*\s*\n?(.*)",
        r"(?:^|\n)FINAL\s*ANSWER[:\s]*\n?(.*)",
    ]:
        match = re.search(pattern, generated, re.DOTALL | re.IGNORECASE)
        if match:
            answer = match.group(1).strip()
            if answer:
                return answer

    # No marker found — return last paragraph as fallback
    paragraphs = [p.strip() for p in generated.strip().split("\n\n") if p.strip()]
    if paragraphs:
        return paragraphs[-1]
    return generated


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
            generated = llm.generate(messages, max_tokens=2048)
        except Exception:
            logger.exception("Answer generation failed for question %s", question.id)
            generated = "Error generating answer."

    # 4. Judge — extract final answer from CoT if present
    score = None
    reasoning = ""
    if judge_llm is not None:
        is_abstention = question.question_type == "abstention" or question.metadata.get(
            "has_answer"
        ) is False
        judge_answer_text = generated
        score, reasoning = judge_answer(
            judge_llm,
            question.question,
            question.expected_answer,
            judge_answer_text,
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


# --- Retrieval-only scoring (no LLM) ---

# Phrases that indicate the model should abstain
_ABSTENTION_MARKERS = {
    "i don't have", "i don't know", "no information", "not mentioned",
    "no relevant", "cannot answer", "not available", "no memories",
}


def _score_retrieval(expected: str, context: str, is_abstention: bool) -> tuple[float, str]:
    """Score retrieved context against expected answer without LLM.

    For normal questions: token F1 between expected answer and retrieved context,
    quantized to 0.0/0.5/1.0.

    For abstention questions: 1.0 if context is empty or lacks relevant info,
    0.0 if context contains plausible-looking content (potential hallucination source).
    """
    expected = str(expected)  # some ground-truth answers are numeric
    context_lower = context.lower()

    if is_abstention:
        # Adversarial question — no correct answer exists in the data.
        # Good retrieval = returning nothing relevant (empty or generic).
        # We check if the expected answer tokens appear (they shouldn't).
        if not context.strip():
            return 1.0, "No context retrieved (correct for adversarial)"
        # If expected is empty, any retrieval is potentially misleading
        if not expected.strip():
            return 0.5, "Context retrieved for unanswerable question"
        f1 = compute_f1(context_lower, expected.lower())
        if f1 < 0.1:
            return 1.0, f"Retrieved context irrelevant to adversarial answer (f1={f1:.2f})"
        return 0.0, f"Retrieved context matches adversarial answer (f1={f1:.2f})"

    # Normal question — check if expected answer is in retrieved context
    if not expected.strip():
        return 0.0, "Empty expected answer"

    # Substring containment check (case-insensitive)
    expected_lower = expected.lower().strip()
    if expected_lower in context_lower:
        return 1.0, f"Exact substring match in context"

    # Token F1 between expected answer and context
    f1 = compute_f1(context_lower, expected_lower)

    # Quantize to 0.0 / 0.5 / 1.0
    if f1 >= 0.5:
        return 1.0, f"Token F1={f1:.2f} (strong match)"
    elif f1 >= 0.2:
        return 0.5, f"Token F1={f1:.2f} (partial match)"
    else:
        return 0.0, f"Token F1={f1:.2f} (no match)"


def evaluate_retrieval(
    question: BenchmarkQuestion,
    search_engine: SearchEngine,
    project: str,
    search_limit: int = 10,
    extra_search_kwargs: dict | None = None,
) -> AnswerResult:
    """Retrieval-only evaluation — no LLM calls.

    1. Search Cairn for relevant memories
    2. Score by checking if retrieved context contains the expected answer
    3. Return AnswerResult with token-F1-based score

    Zero LLM tokens consumed. ~100ms per question (embed + pgvector search).
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

    # 2. Concatenate retrieved content
    context = "\n".join(m.get("content", "") for m in memories)

    # 3. Score
    is_abstention = (
        question.question_type == "abstention"
        or question.metadata.get("has_answer") is False
    )
    score, reasoning = _score_retrieval(
        question.expected_answer, context, is_abstention
    )

    return AnswerResult(
        question_id=question.id,
        question_type=question.question_type,
        expected_answer=question.expected_answer,
        generated_answer=f"[retrieval-only: {len(memories)} memories retrieved]",
        retrieved_memories=[
            {"id": m.get("id"), "content": m.get("content", "")[:200]}
            for m in memories
        ],
        judge_score=score,
        judge_reasoning=reasoning,
    )
