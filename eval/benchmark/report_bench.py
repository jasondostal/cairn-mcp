"""Benchmark-specific reporting: per-type tables and JSON output."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from eval.benchmark.base import BenchmarkResult

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent.parent / "reports"

PUBLISHED_BASELINES = {}


def print_benchmark_results(result: BenchmarkResult) -> None:
    """Print formatted benchmark results table."""
    baselines = PUBLISHED_BASELINES.get(result.benchmark_name, {})

    print()
    print(f"\u2550" * 65)
    print(
        f"  Cairn Benchmark: {result.benchmark_name}  |  "
        f"Strategy: {result.strategy_name}"
    )

    mem_count = result.ingestion_stats.get("memory_count", "?")
    ingest_time = result.ingestion_stats.get("duration_s", "?")
    print(
        f"  Model: {result.model_name}  |  "
        f"Memories: {mem_count}  |  Ingest: {ingest_time}s"
    )
    print(f"\u2550" * 65)

    # Header
    print(f"  {'Question Type':<30} {'Count':>6} {'Accuracy':>10} {'Published':>12}")
    print(f"  {'\u2500' * 60}")

    # Per-type rows
    for qtype, stats in sorted(result.per_type.items()):
        accuracy = stats["accuracy"]
        count = stats["count"]

        # Find published baseline for this type
        published = ""
        type_baselines = baselines.get(qtype, {})
        if type_baselines:
            parts = [f"{name}: {val:.0%}" for name, val in type_baselines.items()]
            published = ", ".join(parts)
        if not published:
            published = "\u2014"

        print(
            f"  {qtype:<30} {count:>6} {accuracy:>9.1%} {published:>12}"
        )

    # Overall
    print(f"  {'\u2500' * 60}")
    overall_published = ""
    overall_baselines = baselines.get("_overall", {})
    if overall_baselines:
        parts = [f"{name}: {val:.0%}" for name, val in overall_baselines.items()]
        overall_published = ", ".join(parts)
    if not overall_published:
        overall_published = "\u2014"

    total_questions = sum(s["count"] for s in result.per_type.values())
    print(
        f"  {'OVERALL':<30} {total_questions:>6} "
        f"{result.overall_accuracy:>9.1%} {overall_published:>12}"
    )
    print(f"\u2550" * 65)
    print()


def write_benchmark_json(result: BenchmarkResult) -> Path:
    """Write benchmark results to a timestamped JSON file."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": datetime.now().isoformat(),
        "benchmark": result.benchmark_name,
        "strategy": result.strategy_name,
        "model": result.model_name,
        "overall_accuracy": result.overall_accuracy,
        "per_type": result.per_type,
        "ingestion_stats": result.ingestion_stats,
        "per_question": [
            {
                "id": r.question_id,
                "type": r.question_type,
                "expected": r.expected_answer,
                "generated": r.generated_answer,
                "score": r.judge_score,
                "reasoning": r.judge_reasoning,
                "memory_count": len(r.retrieved_memories),
            }
            for r in result.per_question
        ],
    }

    path = REPORTS_DIR / f"bench_{result.benchmark_name}_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    logger.info("JSON report written to %s", path)
    return path
