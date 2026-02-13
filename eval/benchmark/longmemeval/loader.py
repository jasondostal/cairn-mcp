"""Parse LongMemEval dataset from local JSON files.

Expected files in eval/benchmark/data/longmemeval/:
  - longmemeval_s.json  (small scale, ~115K tokens)
  - longmemeval_l.json  (large scale, ~1.5M tokens) [optional]
  - OR: questions.json + sessions/ directory

Source: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
GitHub: https://github.com/xiaowu0162/LongMemEval

LongMemEval format — each entry is a 4-tuple:
{
  "question_id": "...",
  "question": "...",
  "answer": "...",
  "question_type": "single-session-user"|"single-session-assistant"|
                   "single-session-preference"|"multi-session"|
                   "knowledge-update"|"temporal-reasoning"|"abstention",
  "haystack_sessions": [
    {
      "session_id": "...",
      "date": "YYYY-MM-DD",
      "conversation": [
        {"role": "user"|"assistant", "content": "..."},
        ...
      ]
    },
    ...
  ],
  "evidence_session_ids": [...],
  "has_answer": true|false
}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from eval.benchmark.base import BenchmarkDataset, BenchmarkQuestion, BenchmarkSession

logger = logging.getLogger(__name__)

# Map scale names to expected filenames
SCALE_FILES = {
    "longmemeval_s": ["longmemeval_s.json", "longmemeval_small.json"],
    "longmemeval_l": ["longmemeval_l.json", "longmemeval_large.json"],
}


def load_longmemeval(
    data_dir: str | Path,
    scale: str = "longmemeval_s",
) -> BenchmarkDataset:
    """Load LongMemEval dataset from directory.

    Args:
        data_dir: Path to the longmemeval data directory.
        scale: Which scale to load — "longmemeval_s" (small) or "longmemeval_l" (large).
    """
    data_dir = Path(data_dir)

    # Find the data file
    candidates = SCALE_FILES.get(scale, [f"{scale}.json"])
    path = None
    for name in candidates:
        candidate = data_dir / name
        if candidate.exists():
            path = candidate
            break

    # Also try a generic filename
    if path is None:
        for name in ["longmemeval.json", "data.json"]:
            candidate = data_dir / name
            if candidate.exists():
                path = candidate
                break

    if path is None:
        raise FileNotFoundError(
            f"LongMemEval dataset not found in {data_dir}. "
            f"Tried: {candidates}. "
            "Download from https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned "
            "and place in eval/benchmark/data/longmemeval/"
        )

    logger.info("Loading LongMemEval (%s) from %s", scale, path)
    raw = json.loads(path.read_text())

    # Handle both list format and dict-with-data format
    if isinstance(raw, dict):
        entries = raw.get("data", raw.get("questions", raw.get("instances", [])))
    elif isinstance(raw, list):
        entries = raw
    else:
        raise ValueError(f"Unexpected top-level type: {type(raw).__name__}")

    if not entries:
        raise ValueError(f"No entries found in {path}")

    # Deduplicate sessions across all questions
    all_sessions: dict[str, BenchmarkSession] = {}
    questions: list[BenchmarkQuestion] = []

    for i, entry in enumerate(entries):
        # Parse question
        qid = str(entry.get("question_id", entry.get("id", i)))
        qtype = entry.get("question_type", entry.get("type", "unknown"))
        qtype = qtype.lower().replace(" ", "-").replace("_", "-")

        has_answer = entry.get("has_answer", True)
        # Abstention type override
        if not has_answer and qtype != "abstention":
            qtype = "abstention"

        metadata = {
            "has_answer": has_answer,
            "evidence_session_ids": entry.get("evidence_session_ids", []),
        }
        if "question_date" in entry:
            metadata["question_date"] = entry["question_date"]

        questions.append(BenchmarkQuestion(
            id=f"lme_{qid}",
            question=entry.get("question", ""),
            expected_answer=entry.get("answer", entry.get("gold_answer", "")),
            question_type=qtype,
            metadata=metadata,
        ))

        # Parse haystack sessions (deduplicate by session_id)
        haystack = entry.get("haystack_sessions", entry.get("sessions", []))
        for sess in haystack:
            sid = str(sess.get("session_id", sess.get("id", "")))
            if sid in all_sessions:
                continue  # Already seen this session

            conv = sess.get("conversation", sess.get("turns", []))
            turns = []
            for turn in conv:
                turns.append({
                    "role": turn.get("role", "user"),
                    "content": turn.get("content", turn.get("text", "")),
                })

            all_sessions[sid] = BenchmarkSession(
                session_id=sid,
                turns=turns,
                date=sess.get("date"),
            )

    sessions = list(all_sessions.values())
    logger.info(
        "LongMemEval loaded: %d sessions, %d questions",
        len(sessions),
        len(questions),
    )
    return BenchmarkDataset(
        name=scale,
        sessions=sessions,
        questions=questions,
    )
