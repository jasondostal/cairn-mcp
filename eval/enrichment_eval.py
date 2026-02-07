"""Enrichment accuracy measurement.

Uses the real Enricher + configured LLM backend on annotated samples.
Measures tag recall, importance accuracy, and type accuracy.
Skips with a clear message if no LLM backend is available.
"""

import json
import logging
from pathlib import Path

from cairn.config import load_config
from cairn.core.enrichment import Enricher

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"


def load_ground_truth(path: Path | None = None) -> list[dict]:
    """Load enrichment ground truth annotations.

    Each sample has:
        content: the memory text
        expected_tags: list of expected tags (lowercase)
        importance_range: [low, high] acceptable range
        expected_types: list of acceptable memory types
    """
    path = path or DATA_DIR / "enrichment_ground_truth.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Ground truth not found: {path}\n"
            "Create eval/data/enrichment_ground_truth.json with annotated samples."
        )

    data = json.loads(path.read_text())
    if "samples" not in data:
        raise ValueError("Ground truth must contain 'samples' key")

    return data["samples"]


def run_enrichment_eval(path: Path | None = None) -> dict:
    """Run enrichment accuracy evaluation.

    Returns:
        {
            "metrics": {
                "tag_recall": float,
                "importance_accuracy": float,
                "type_accuracy": float,
                "overall": float,
            },
            "sample_count": int,
            "per_sample": [...]
        }
    """
    samples = load_ground_truth(path)

    # Try to initialize the enricher
    config = load_config()
    try:
        if config.llm.backend == "bedrock":
            from cairn.llm.bedrock import BedrockLLM
            llm = BedrockLLM(config.llm)
        elif config.llm.backend == "ollama":
            from cairn.llm.ollama import OllamaLLM
            llm = OllamaLLM(config.llm)
        else:
            raise ValueError(f"Unknown LLM backend: {config.llm.backend}")
    except Exception as e:
        logger.warning("LLM backend not available: %s", e)
        raise RuntimeError(
            f"Enrichment eval requires a working LLM backend. "
            f"Current backend '{config.llm.backend}' failed: {e}"
        ) from e

    enricher = Enricher(llm)

    tag_recalls = []
    importance_hits = []
    type_hits = []
    per_sample = []

    for sample in samples:
        content = sample["content"]
        result = enricher.enrich(content)

        if not result:
            # Enrichment failed entirely for this sample
            per_sample.append({
                "content_preview": content[:80],
                "enrichment_failed": True,
            })
            tag_recalls.append(0.0)
            importance_hits.append(0)
            type_hits.append(0)
            continue

        # Tag recall: |predicted ∩ expected| / |expected|
        predicted_tags = set(result.get("tags", []))
        expected_tags = set(sample.get("expected_tags", []))
        if expected_tags:
            tag_recall = len(predicted_tags & expected_tags) / len(expected_tags)
        else:
            tag_recall = 1.0
        tag_recalls.append(tag_recall)

        # Importance accuracy: within [low, high] range
        predicted_importance = result.get("importance", 0.5)
        importance_range = sample.get("importance_range", [0.0, 1.0])
        importance_hit = importance_range[0] <= predicted_importance <= importance_range[1]
        importance_hits.append(int(importance_hit))

        # Type accuracy: matches any expected type
        predicted_type = result.get("memory_type", "")
        expected_types = sample.get("expected_types", [])
        type_hit = predicted_type in expected_types if expected_types else True
        type_hits.append(int(type_hit))

        per_sample.append({
            "content_preview": content[:80],
            "tag_recall": round(tag_recall, 4),
            "importance_ok": importance_hit,
            "type_ok": type_hit,
            "predicted": {
                "tags": list(predicted_tags),
                "importance": predicted_importance,
                "memory_type": predicted_type,
            },
        })

    n = len(samples)
    metrics = {
        "tag_recall": round(sum(tag_recalls) / n, 4) if n else 0.0,
        "importance_accuracy": round(sum(importance_hits) / n, 4) if n else 0.0,
        "type_accuracy": round(sum(type_hits) / n, 4) if n else 0.0,
    }
    metrics["overall"] = round(
        (metrics["tag_recall"] + metrics["importance_accuracy"] + metrics["type_accuracy"]) / 3,
        4,
    )

    return {
        "metrics": metrics,
        "sample_count": n,
        "per_sample": per_sample,
    }
