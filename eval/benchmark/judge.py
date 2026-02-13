"""LLM-as-judge scoring for benchmark QA evaluation.

Scores: 0.0 (wrong), 0.5 (partially correct), 1.0 (correct).
Special handling for abstention questions.

Default judge: Cairn's configured LLM (Llama 3.2 90B via Bedrock).
Override with --judge-model flag in CLI.
"""

from __future__ import annotations

import logging
import re

from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

# Standard judge prompt adapted from LongMemEval / LoCoMo papers
JUDGE_SYSTEM = """\
You are an impartial judge evaluating the quality of an AI assistant's answer \
to a question about past conversations.

You will be given:
- The question
- The expected (gold) answer
- The assistant's generated answer

Score the answer:
- 1.0: The generated answer is correct and captures the key information from the expected answer.
- 0.5: The generated answer is partially correct — it contains some relevant information but misses key details or includes inaccuracies.
- 0.0: The generated answer is incorrect, irrelevant, or fails to answer the question.

Respond with EXACTLY this format (no other text):
Score: <0.0|0.5|1.0>
Reasoning: <one sentence explanation>"""

JUDGE_USER = """\
Question: {question}

Expected answer: {expected}

Generated answer: {generated}"""

# For abstention questions — model should decline to answer
ABSTENTION_SYSTEM = """\
You are an impartial judge evaluating whether an AI assistant correctly \
identified that a question cannot be answered from the available information.

The question is designed to have NO answer in the conversation history. \
The correct behavior is to decline, say "I don't know", or indicate the \
information is not available.

Score the answer:
- 1.0: The assistant correctly declined to answer or indicated the information is not available.
- 0.5: The assistant expressed uncertainty but still attempted an answer.
- 0.0: The assistant confidently gave an answer (which would be fabricated/hallucinated).

Respond with EXACTLY this format (no other text):
Score: <0.0|0.5|1.0>
Reasoning: <one sentence explanation>"""


def judge_answer(
    llm: LLMInterface,
    question: str,
    expected: str,
    generated: str,
    is_abstention: bool = False,
) -> tuple[float, str]:
    """Score a generated answer against the expected answer.

    Args:
        llm: LLM backend for judging.
        question: The benchmark question.
        expected: Gold standard answer.
        generated: Model's generated answer.
        is_abstention: If True, use abstention scoring (correct = decline).

    Returns:
        (score, reasoning) tuple.
    """
    system = ABSTENTION_SYSTEM if is_abstention else JUDGE_SYSTEM
    user_msg = JUDGE_USER.format(
        question=question,
        expected=expected,
        generated=generated,
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    try:
        response = llm.generate(messages, max_tokens=200)
        return _parse_judge_response(response)
    except Exception:
        logger.exception("Judge call failed")
        return 0.0, "Judge error"


def _parse_judge_response(response: str) -> tuple[float, str]:
    """Parse Score: and Reasoning: from judge response."""
    score_match = re.search(r"Score:\s*([\d.]+)", response)
    reasoning_match = re.search(r"Reasoning:\s*(.+)", response, re.DOTALL)

    if not score_match:
        logger.warning("Could not parse judge score from: %s", response[:200])
        return 0.0, f"Parse error: {response[:200]}"

    raw_score = float(score_match.group(1))
    # Clamp to valid values
    if raw_score >= 0.75:
        score = 1.0
    elif raw_score >= 0.25:
        score = 0.5
    else:
        score = 0.0

    reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
    return score, reasoning
