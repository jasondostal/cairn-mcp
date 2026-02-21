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
You are an impartial judge evaluating an AI assistant's answer about past conversations.

You will be given: a question, the expected (gold) answer, and the generated answer.

SCORING RULES:
- 1.0: The generated answer captures the key information from the expected answer. \
Be generous — as long as it touches the same topic/fact, count it as correct. \
Different phrasing, extra detail, or longer answers are fine.
- 0.5: Partially correct — relevant information but misses key details.
- 0.0: Incorrect, irrelevant, or completely fails to answer.

SPECIAL CASES:
- Time/dates: "May 7th" vs "7 May" vs "May 2023" are equivalent if same date. \
"last year" resolved to the correct year counts as correct.
- Short gold answers: If gold is "No" and generated says "No, because X" → 1.0.
- Person corrections: If the generated answer correctly notes the question has the wrong \
person (e.g., "That was Caroline, not Melanie") → 1.0 if the underlying fact is right.
- Empty gold answer: If gold answer is empty/blank, the question is adversarial — \
the correct behavior is to decline, correct the attribution, or say nothing applies. \
Score 1.0 if the assistant declines or corrects attribution.

You MUST start your response with the score line. No preamble, no thinking, no explanation before it.

Score: <0.0|0.5|1.0>
Reasoning: <one sentence>"""

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

You MUST start your response with the score line. No preamble, no thinking, no explanation before it.

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
        response = llm.generate(messages, max_tokens=400)
        return _parse_judge_response(response)
    except Exception:
        logger.exception("Judge call failed")
        return 0.0, "Judge error"


def _parse_judge_response(response: str) -> tuple[float, str]:
    """Parse Score: and Reasoning: from judge response.

    Handles reasoning models that emit thinking text before the score.
    Falls back to scanning for bare score patterns (e.g. "1.0", "0.5").
    """
    score_match = re.search(r"Score:\s*([\d.]+)", response)
    reasoning_match = re.search(r"Reasoning:\s*(.+)", response, re.DOTALL)

    # Fallback: some models output just the number or "score is 1.0"
    if not score_match:
        score_match = re.search(r"\b(1\.0|0\.5|0\.0)\b", response)

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
