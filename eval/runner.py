"""CLI entry point for the eval framework.

Usage:
    python -m eval.runner                        # Full eval: all models + enrichment
    python -m eval.runner --search-only          # Skip enrichment
    python -m eval.runner --enrichment-only      # Skip search/model comparison
    python -m eval.runner --models minilm        # Single model
    python -m eval.runner --models minilm mpnet  # Specific models
    python -m eval.runner --json                 # Write JSON report to eval/reports/
    python -m eval.runner --keep-dbs             # Don't drop eval databases
"""

import argparse
import logging
import os
import sys

from eval.model_compare import MODEL_REGISTRY, run_model_comparison
from eval.report import (
    print_enrichment_results,
    print_model_comparison,
    print_search_results,
    write_json_report,
)

logger = logging.getLogger(__name__)


def _build_admin_dsn() -> str:
    """Build admin DSN from environment or defaults.

    The admin DSN connects to the 'postgres' database for CREATE/DROP DATABASE.
    """
    host = os.getenv("CAIRN_DB_HOST", "localhost")
    port = os.getenv("CAIRN_DB_PORT", "5432")
    user = os.getenv("CAIRN_DB_USER", "cairn")
    password = os.getenv("CAIRN_DB_PASS", "cairn")
    return f"postgresql://{user}:{password}@{host}:{port}/postgres"


def main():
    parser = argparse.ArgumentParser(
        description="Cairn eval framework — search quality and model comparison",
    )
    parser.add_argument(
        "--search-only", action="store_true",
        help="Run only search evaluation (skip enrichment)",
    )
    parser.add_argument(
        "--enrichment-only", action="store_true",
        help="Run only enrichment evaluation (skip search)",
    )
    parser.add_argument(
        "--models", nargs="+", default=None,
        help=f"Models to evaluate. Available: {', '.join(MODEL_REGISTRY.keys())}",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Write JSON report to eval/reports/",
    )
    parser.add_argument(
        "--keep-dbs", action="store_true",
        help="Don't drop eval databases after evaluation",
    )
    parser.add_argument(
        "--k", type=int, default=10,
        help="Number of results to evaluate (default: 10)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    admin_dsn = _build_admin_dsn()

    # Validate model selection
    models = args.models
    if models:
        for m in models:
            if m not in MODEL_REGISTRY:
                print(f"Unknown model: {m}. Available: {', '.join(MODEL_REGISTRY.keys())}")
                sys.exit(1)
    else:
        models = list(MODEL_REGISTRY.keys())

    search_results = []
    enrichment_results = None

    # Search evaluation
    if not args.enrichment_only:
        print(f"\nRunning search eval for models: {', '.join(models)}")
        print(f"Results at k={args.k}")
        print()

        search_results = run_model_comparison(
            admin_dsn=admin_dsn,
            model_names=models,
            k=args.k,
            keep_dbs=args.keep_dbs,
        )

        print_search_results(search_results)
        if len(search_results) > 1:
            print_model_comparison(search_results)

    # Enrichment evaluation
    if not args.search_only:
        try:
            from eval.enrichment_eval import run_enrichment_eval
            print("\nRunning enrichment evaluation...")
            enrichment_results = run_enrichment_eval()
            print_enrichment_results(enrichment_results)
        except FileNotFoundError as e:
            print(f"\nSkipping enrichment eval: {e}")
        except Exception as e:
            print(f"\nEnrichment eval failed: {e}")
            logger.exception("Enrichment eval error")

    # JSON report
    if args.json and (search_results or enrichment_results):
        path = write_json_report(search_results, enrichment_results)
        print(f"\nJSON report: {path}")

    print()


if __name__ == "__main__":
    main()
