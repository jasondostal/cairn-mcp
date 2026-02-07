"""Console table and JSON report output."""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent / "reports"

# recall@10 target from PRD
RECALL_TARGET = 0.80


def print_search_results(results: list[dict]) -> None:
    """Print search eval results as a formatted console table.

    Each result dict is from run_search_eval() for one model.
    """
    if not results:
        print("No search results to display.")
        return

    for result in results:
        model = result["model"]
        dims = result["dimensions"]
        embed_time = result.get("embed_time_s", "?")

        print(f"\n{'=' * 70}")
        print(f"  Model: {model} ({dims}-dim)  |  Embed time: {embed_time}s")
        print(f"{'=' * 70}")

        # Header
        print(f"  {'Mode':<12} {'Recall@10':>10} {'Prec@10':>10} {'MRR':>10} {'NDCG@10':>10}")
        print(f"  {'-' * 54}")

        for mode in ["semantic", "keyword", "vector"]:
            metrics = result["modes"].get(mode, {})
            recall = metrics.get("recall@k", 0)
            precision = metrics.get("precision@k", 0)
            mrr_val = metrics.get("mrr", 0)
            ndcg = metrics.get("ndcg@k", 0)

            # Mark recall with pass/fail indicator
            indicator = " *" if recall >= RECALL_TARGET else " !"
            print(
                f"  {mode:<12} {recall:>9.1%}{indicator}"
                f" {precision:>9.1%} {mrr_val:>10.4f} {ndcg:>10.4f}"
            )

        print()
        print(f"  Target: recall@10 >= {RECALL_TARGET:.0%}   (* = pass, ! = below target)")


def print_model_comparison(results: list[dict]) -> None:
    """Print side-by-side model comparison for hybrid (semantic) mode."""
    if len(results) < 2:
        return

    print(f"\n{'=' * 70}")
    print("  Model Comparison — Hybrid (semantic) mode")
    print(f"{'=' * 70}")

    header = f"  {'Metric':<14}"
    for r in results:
        header += f" {r['model']:>12}"
    print(header)
    print(f"  {'-' * (14 + 13 * len(results))}")

    metrics_order = ["recall@k", "precision@k", "mrr", "ndcg@k"]
    labels = {"recall@k": "Recall@10", "precision@k": "Precision@10", "mrr": "MRR", "ndcg@k": "NDCG@10"}

    for metric in metrics_order:
        row = f"  {labels[metric]:<14}"
        values = []
        for r in results:
            val = r["modes"].get("semantic", {}).get(metric, 0)
            values.append(val)
            row += f" {val:>11.1%}" if metric.startswith(("recall", "precision")) else f" {val:>11.4f}"
        print(row)

    # Keyword control check
    print()
    keyword_vals = [r["modes"].get("keyword", {}).get("recall@k", 0) for r in results]
    if len(set(round(v, 4) for v in keyword_vals)) == 1:
        print("  Keyword control check: PASS (identical across models)")
    else:
        print("  Keyword control check: WARN (scores differ — investigate)")
        for r, v in zip(results, keyword_vals):
            print(f"    {r['model']}: {v:.4f}")


def print_enrichment_results(results: dict) -> None:
    """Print enrichment eval results."""
    print(f"\n{'=' * 70}")
    print("  Enrichment Accuracy")
    print(f"{'=' * 70}")

    metrics = results.get("metrics", {})
    print(f"  {'Tag recall':<20} {metrics.get('tag_recall', 0):>10.1%}")
    print(f"  {'Importance accuracy':<20} {metrics.get('importance_accuracy', 0):>10.1%}")
    print(f"  {'Type accuracy':<20} {metrics.get('type_accuracy', 0):>10.1%}")
    print(f"  {'Overall':<20} {metrics.get('overall', 0):>10.1%}")

    n = results.get("sample_count", 0)
    print(f"\n  Samples evaluated: {n}")
    print(f"  Target: overall >= {RECALL_TARGET:.0%}")


def write_json_report(
    search_results: list[dict],
    enrichment_results: dict | None = None,
) -> Path:
    """Write full results to a timestamped JSON file."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": datetime.now().isoformat(),
        "search": search_results,
    }
    if enrichment_results:
        report["enrichment"] = enrichment_results

    path = REPORTS_DIR / f"eval_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    logger.info("JSON report written to %s", path)
    return path
