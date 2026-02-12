"""Allow running as `python -m eval`.

Routes to either the original search eval or the benchmark eval
based on the first argument.

Usage:
    python -m eval                    # Original search/enrichment eval
    python -m eval benchmark locomo   # Benchmark evaluation
"""

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "benchmark":
        # Forward to benchmark runner, stripping "benchmark" from argv
        from eval.benchmark.runner_bench import main as bench_main
        bench_main(sys.argv[2:])
    else:
        from eval.runner import main as search_main
        search_main()


main()
