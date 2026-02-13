"""Parse LoCoMo dataset from local JSON.

Expected file: eval/benchmark/data/locomo/locomo10.json
Source: https://github.com/snap-research/locomo

Actual LoCoMo format (10 conversations):
[
  {
    "sample_id": N,
    "conversation": {
      "speaker_a": "Name",
      "speaker_b": "Name",
      "session_1_date_time": "...",
      "session_1": [{"speaker": "Name", "dia_id": "D1:1", "text": "..."}, ...],
      "session_2_date_time": "...",
      "session_2": [...],
      ...
    },
    "qa": [
      {"question": "...", "answer": "...", "evidence": ["D1:3"], "category": 1-5},
      ...
    ],
    "event_summary": {...},
    "observation": {...},
    "session_summary": {...}
  },
  ...
]

Categories: 1=single-hop, 2=multi-hop, 3=temporal, 4=open-domain, 5=adversarial
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from eval.benchmark.base import BenchmarkDataset, BenchmarkQuestion, BenchmarkSession

logger = logging.getLogger(__name__)

CATEGORY_MAP = {
    1: "single-hop",
    2: "multi-hop",
    3: "temporal",
    4: "open-domain",
    5: "adversarial",
}


def load_locomo(data_dir: str | Path) -> BenchmarkDataset:
    """Load LoCoMo dataset from directory."""
    data_dir = Path(data_dir)

    for name in ["locomo10.json", "locomo.json"]:
        path = data_dir / name
        if path.exists():
            break
    else:
        raise FileNotFoundError(
            f"LoCoMo dataset not found in {data_dir}. "
            "Download from https://github.com/snap-research/locomo "
            "and place locomo10.json in eval/benchmark/data/locomo/"
        )

    logger.info("Loading LoCoMo from %s", path)
    raw = json.loads(path.read_text())

    if not isinstance(raw, list):
        raise ValueError(f"Expected top-level list, got {type(raw).__name__}")

    sessions = []
    questions = []
    q_id_counter = 0

    for conv in raw:
        sample_id = str(conv.get("sample_id", ""))
        conv_data = conv.get("conversation", {})

        speaker_a = conv_data.get("speaker_a", "User")
        speaker_b = conv_data.get("speaker_b", "Assistant")

        # Extract sessions: keys like session_1, session_2, ...
        session_keys = sorted(
            [k for k in conv_data.keys() if re.match(r"session_\d+$", k)],
            key=lambda k: int(k.split("_")[1]),
        )

        for skey in session_keys:
            turns_raw = conv_data[skey]
            date_key = f"{skey}_date_time"
            date = conv_data.get(date_key)

            formatted_turns = []
            for turn in turns_raw:
                speaker = turn.get("speaker", "")
                # Map speaker names to roles
                if speaker == speaker_a:
                    role = "user"
                elif speaker == speaker_b:
                    role = "assistant"
                else:
                    role = "user"

                formatted_turns.append({
                    "role": role,
                    "speaker": speaker,
                    "content": turn.get("text", ""),
                })

            sessions.append(BenchmarkSession(
                session_id=f"s{sample_id}_{skey}",
                turns=formatted_turns,
                date=date,
            ))

        # Parse QA pairs
        qa_list = conv.get("qa", [])
        for qa in qa_list:
            q_id_counter += 1
            cat_num = qa.get("category", 0)
            category = CATEGORY_MAP.get(cat_num, f"unknown-{cat_num}")

            metadata = {
                "conversation_id": sample_id,
                "evidence": qa.get("evidence", []),
            }
            if category == "adversarial":
                metadata["has_answer"] = False

            questions.append(BenchmarkQuestion(
                id=f"locomo_{q_id_counter}",
                question=qa.get("question", ""),
                expected_answer=qa.get("answer", ""),
                question_type=category,
                metadata=metadata,
            ))

    logger.info(
        "LoCoMo loaded: %d sessions, %d questions from %d conversations",
        len(sessions),
        len(questions),
        len(raw),
    )
    return BenchmarkDataset(name="locomo", sessions=sessions, questions=questions)
