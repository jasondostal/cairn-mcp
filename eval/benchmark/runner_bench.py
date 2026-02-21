"""CLI orchestrator for benchmark evaluation.

Usage:
    python -m eval benchmark longmemeval_s
    python -m eval benchmark locomo
    python -m eval benchmark longmemeval_s --strategy raw_turns
    python -m eval benchmark longmemeval_s --max-questions 20
    python -m eval benchmark longmemeval_s --types temporal-reasoning
    python -m eval benchmark longmemeval_s --models minilm mpnet
    python -m eval benchmark longmemeval_s --json --keep-dbs
    python -m eval benchmark --download longmemeval
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg

from eval.benchmark.base import BenchmarkAdapter, BenchmarkResult, IngestStrategy
from eval.benchmark.locomo.adapter import LoCoMoAdapter
from eval.benchmark.longmemeval.adapter import LongMemEvalAdapter
from eval.benchmark.qa_metrics import compute_accuracy, compute_per_type
from eval.benchmark.rag import evaluate_question, evaluate_retrieval
from eval.benchmark.report_bench import print_benchmark_results, write_benchmark_json
from eval.corpus import create_eval_db, drop_eval_db
from eval.model_compare import MODEL_REGISTRY
from eval.utils import build_admin_dsn, replace_dbname

logger = logging.getLogger(__name__)

# Benchmark registry
BENCHMARKS: dict[str, type[BenchmarkAdapter]] = {
    "locomo": LoCoMoAdapter,
    "longmemeval_s": LongMemEvalAdapter,
    "longmemeval_l": LongMemEvalAdapter,
}

# Strategy registry
STRATEGIES = {
    "llm_extract": "eval.benchmark.strategies.llm_extract:LLMExtractStrategy",
    "two_pass": "eval.benchmark.strategies.two_pass:TwoPassStrategy",
    "raw_turns": "eval.benchmark.strategies.raw_turns:RawTurnsStrategy",
    "session_summary": "eval.benchmark.strategies.session_summary:SessionSummaryStrategy",
}

# Default data directory
DATA_DIR_BASE = "eval/benchmark/data"


def _get_adapter(benchmark_name: str) -> BenchmarkAdapter:
    """Create the appropriate adapter for a benchmark."""
    if benchmark_name.startswith("longmemeval"):
        return LongMemEvalAdapter(scale=benchmark_name)
    elif benchmark_name == "locomo":
        return LoCoMoAdapter()
    else:
        raise ValueError(
            f"Unknown benchmark: {benchmark_name}. "
            f"Available: {', '.join(BENCHMARKS.keys())}"
        )


def _get_strategy(strategy_name: str, llm=None) -> IngestStrategy:
    """Create the appropriate ingestion strategy."""
    if strategy_name == "raw_turns":
        from eval.benchmark.strategies.raw_turns import RawTurnsStrategy
        return RawTurnsStrategy()
    elif strategy_name == "llm_extract":
        from eval.benchmark.strategies.llm_extract import LLMExtractStrategy
        if llm is None:
            raise ValueError("llm_extract strategy requires an LLM backend")
        return LLMExtractStrategy(llm)
    elif strategy_name == "two_pass":
        from eval.benchmark.strategies.two_pass import TwoPassStrategy
        if llm is None:
            raise ValueError("two_pass strategy requires an LLM backend")
        return TwoPassStrategy(llm)
    elif strategy_name == "session_summary":
        from eval.benchmark.strategies.session_summary import SessionSummaryStrategy
        if llm is None:
            raise ValueError("session_summary strategy requires an LLM backend")
        return SessionSummaryStrategy(llm)
    else:
        raise ValueError(
            f"Unknown strategy: {strategy_name}. "
            f"Available: {', '.join(STRATEGIES.keys())}"
        )


def _create_services(eval_dsn: str, model_spec: dict, skip_enricher: bool = False, pool_size: int = 10):
    """Create minimal Cairn services for benchmark evaluation.

    Returns (search_engine, memory_store, llm) tuple.
    """
    from cairn.config import (
        Config,
        DatabaseConfig,
        EmbeddingConfig,
        LLMCapabilities,
        LLMConfig,
        load_config,
    )
    from cairn.core.enrichment import Enricher
    from cairn.core.memory import MemoryStore
    from cairn.core.search import SearchEngine
    from cairn.embedding import get_embedding_engine
    from cairn.llm import get_llm
    from cairn.storage import database as db_module
    from cairn.storage.database import Database

    # Parse eval DSN for database config
    # Format: postgresql://user:pass@host:port/dbname
    parts = eval_dsn.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")

    db_config = DatabaseConfig(
        host=host_port[0],
        port=int(host_port[1]) if len(host_port) > 1 else 5432,
        name=host_port_db[1],
        user=user_pass[0],
        password=user_pass[1] if len(user_pass) > 1 else "",
    )

    # Load base config for LLM settings, override DB and embedding
    config = load_config()

    backend = model_spec.get("backend", "local")
    if backend == "bedrock":
        embedding_config = EmbeddingConfig(
            backend="bedrock",
            bedrock_model=model_spec["hf_id"],
            dimensions=model_spec["dimensions"],
        )
    else:
        embedding_config = EmbeddingConfig(
            model=model_spec["hf_id"],
            dimensions=model_spec["dimensions"],
        )

    # Override pool size for parallel benchmark workers
    db_module.POOL_MAX_SIZE = max(pool_size, db_module.POOL_MAX_SIZE)
    db_module.POOL_MIN_SIZE = min(4, db_module.POOL_MAX_SIZE)

    db = Database(db_config)
    db.connect()
    embedding = get_embedding_engine(embedding_config)

    # LLM — use configured backend
    llm = None
    try:
        llm = get_llm(config.llm)
    except Exception:
        logger.warning("LLM not available — strategies requiring LLM will fail")

    import os as _os
    capabilities = LLMCapabilities(
        relationship_extract=False,  # Skip for benchmarks
        rule_conflict_check=False,
        session_synthesis=False,
        consolidation=False,
        confidence_gating=False,
        reranking=_os.getenv("CAIRN_RERANKING", "false").lower() in ("true", "1", "yes"),
        type_routing=_os.getenv("CAIRN_TYPE_ROUTING", "false").lower() in ("true", "1", "yes"),
        spreading_activation=_os.getenv("CAIRN_SPREADING_ACTIVATION", "false").lower() in ("true", "1", "yes"),
        mca_gate=_os.getenv("CAIRN_MCA_GATE", "false").lower() in ("true", "1", "yes"),
        search_v2=_os.getenv("CAIRN_SEARCH_V2", "false").lower() in ("true", "1", "yes"),
        knowledge_extraction=_os.getenv("CAIRN_KNOWLEDGE_EXTRACTION", "false").lower() in ("true", "1", "yes"),
    )

    enricher = Enricher(llm) if (llm and not skip_enricher) else None

    # Reranker for benchmark
    reranker = None
    if capabilities.reranking:
        from cairn.core.reranker import get_reranker
        reranker = get_reranker(config.reranker)

    rerank_candidates = config.reranker.candidates

    # Activation engine for benchmark
    activation_engine = None
    if capabilities.spreading_activation:
        from cairn.core.activation import ActivationEngine
        activation_engine = ActivationEngine(db)

    # Knowledge extractor — requires graph + LLM
    knowledge_extractor = None
    graph = None
    if capabilities.knowledge_extraction and llm:
        try:
            from cairn.core.extraction import KnowledgeExtractor
            from cairn.graph import get_graph_provider

            graph = get_graph_provider()
            if graph:
                graph.connect()
                graph.ensure_schema()
                knowledge_extractor = KnowledgeExtractor(llm, embedding, graph)
                logger.info("Knowledge extraction enabled for benchmark")
            else:
                logger.warning("Knowledge extraction requested but no graph provider")
        except Exception:
            logger.warning("Knowledge extractor init failed", exc_info=True)

    memory_store = MemoryStore(
        db, embedding,
        enricher=enricher,
        llm=llm,
        capabilities=capabilities,
        knowledge_extractor=knowledge_extractor,
    )
    search_engine = SearchEngine(
        db, embedding,
        llm=llm,
        capabilities=capabilities,
        reranker=reranker,
        rerank_candidates=rerank_candidates,
        activation_engine=activation_engine,
    )

    # SearchV2 — graph-primary search with Neo4j entity traversal
    use_search_v2 = _os.getenv("CAIRN_SEARCH_V2", "false").lower() in ("true", "1", "yes")
    if use_search_v2:
        try:
            from cairn.core.search_v2 import SearchV2

            # Reuse graph from knowledge extractor if available, else init fresh
            if not graph:
                from cairn.graph import get_graph_provider
                graph = get_graph_provider()
                if graph:
                    graph.connect()
                    graph.ensure_schema()
            if graph:
                search_engine = SearchV2(
                    db=db,
                    embedding=embedding,
                    graph=graph,
                    llm=llm,
                    capabilities=capabilities,
                    reranker=reranker,
                    rerank_candidates=rerank_candidates,
                    fallback_engine=search_engine,
                )
                logger.info("Benchmark using SearchV2 (intent-routed)")
            else:
                logger.warning("SearchV2 requested but no graph provider — using legacy search")
        except Exception:
            logger.warning("SearchV2 init failed — using legacy search", exc_info=True)

    return search_engine, memory_store, llm


def _db_exists(admin_dsn: str, db_name: str) -> bool:
    """Check if a database exists."""
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        return row is not None


def _count_memories(dsn: str) -> int:
    """Count memories in an eval database."""
    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT count(*) FROM memories").fetchone()
        return row[0] if row else 0


def run_benchmark(
    benchmark_name: str,
    strategy_name: str = "llm_extract",
    model_names: list[str] | None = None,
    max_questions: int | None = None,
    question_types: list[str] | None = None,
    keep_dbs: bool = False,
    reuse_db: bool = False,
    no_enrich: bool = False,
    write_json: bool = False,
    verbose: bool = False,
    search_limit: int = 10,
    workers: int = 1,
    conversation_filter: str | None = None,
    scorer: str = "llm",
    judge_model: str | None = None,
) -> list[BenchmarkResult]:
    """Run a benchmark evaluation.

    Returns list of BenchmarkResult (one per model).
    """
    admin_dsn = build_admin_dsn()

    if model_names is None:
        model_names = ["minilm"]

    adapter = _get_adapter(benchmark_name)

    # Determine data directory
    if benchmark_name.startswith("longmemeval"):
        data_subdir = "longmemeval"
    else:
        data_subdir = benchmark_name
    data_dir = f"{DATA_DIR_BASE}/{data_subdir}"

    # Load dataset
    print(f"\nLoading {benchmark_name} dataset...")
    dataset = adapter.load(data_dir)
    print(f"  Sessions: {len(dataset.sessions)}, Questions: {len(dataset.questions)}")

    # Filter questions if needed
    questions = dataset.questions
    if conversation_filter:
        questions = [q for q in questions if q.metadata.get("conversation_id") == conversation_filter]
        print(f"  Filtered to conversation {conversation_filter}: {len(questions)} questions")
    if question_types:
        questions = [q for q in questions if q.question_type in question_types]
        print(f"  Filtered to types {question_types}: {len(questions)} questions")
    if max_questions:
        questions = questions[:max_questions]
        print(f"  Limited to {max_questions} questions")

    results = []

    for model_name in model_names:
        if model_name not in MODEL_REGISTRY:
            print(f"Unknown model: {model_name}, skipping")
            continue

        model_spec = MODEL_REGISTRY[model_name]
        # Include strategy in DB name to avoid overwriting different ingestions
        strategy_suffix = f"_{strategy_name}" if strategy_name != "llm_extract" else ""
        db_name = f"cairn_eval_{benchmark_name}_{model_name}{strategy_suffix}"

        print(f"\n--- Model: {model_name} ({model_spec['dimensions']}-dim) ---")

        eval_dsn = replace_dbname(admin_dsn, db_name)
        ingest_stats = {}

        if reuse_db and _db_exists(admin_dsn, db_name):
            mem_count = _count_memories(eval_dsn)
            print(f"  Reusing existing database: {db_name} ({mem_count} memories)")
            ingest_stats = {"memory_count": mem_count, "duration_s": 0, "reused": True}
        else:
            # Create eval database
            print("  Creating eval database...")
            create_eval_db(admin_dsn, db_name, model_spec["dimensions"])

        try:
            # Initialize services
            search_engine, memory_store, llm = _create_services(
                eval_dsn, model_spec, skip_enricher=no_enrich,
                pool_size=max(workers + 2, 10),
            )

            # Ingest (skip if reusing)
            if not ingest_stats.get("reused"):
                strategy = _get_strategy(strategy_name, llm)
                ingest_sessions = dataset.sessions
                if conversation_filter:
                    prefix = f"s{conversation_filter}_"
                    ingest_sessions = [s for s in ingest_sessions if s.session_id.startswith(prefix)]
                    print(f"  Filtered sessions to {conversation_filter}: {len(ingest_sessions)} sessions")
                print(f"  Ingesting with strategy: {strategy.name}...")
                ingest_stats = strategy.ingest(ingest_sessions, memory_store, project="benchmark")
                print(
                    f"  Ingested: {ingest_stats.get('memory_count', '?')} memories "
                    f"in {ingest_stats.get('duration_s', '?')}s"
                )

            # Evaluate
            use_retrieval_scorer = scorer == "retrieval"
            if use_retrieval_scorer:
                judge_llm = None
            elif judge_model:
                from cairn.config import LLMConfig
                from cairn.llm import get_llm as _get_judge_llm
                import os as _judge_os
                judge_config = LLMConfig(
                    backend="openai",
                    openai_base_url=_judge_os.getenv("CAIRN_OPENAI_BASE_URL", "https://api.openai.com"),
                    openai_model=judge_model,
                    openai_api_key=_judge_os.getenv("CAIRN_OPENAI_API_KEY", ""),
                )
                judge_llm = _get_judge_llm(judge_config)
                logger.info("Separate judge LLM: %s", judge_model)
            else:
                judge_llm = llm
            effective_workers = min(workers, len(questions))
            parallel_note = f" ({effective_workers} workers)" if effective_workers > 1 else ""
            scorer_note = " [retrieval scorer — no LLM]" if use_retrieval_scorer else ""
            print(f"  Evaluating {len(questions)} questions{parallel_note}{scorer_note}...")

            def _eval_single(question):
                extra_kwargs = adapter.get_search_kwargs(question)
                if use_retrieval_scorer:
                    return evaluate_retrieval(
                        question=question,
                        search_engine=search_engine,
                        project="benchmark",
                        search_limit=search_limit,
                        extra_search_kwargs=extra_kwargs,
                    )
                return evaluate_question(
                    question=question,
                    search_engine=search_engine,
                    llm=llm,
                    judge_llm=judge_llm,
                    project="benchmark",
                    search_limit=search_limit,
                    extra_search_kwargs=extra_kwargs,
                )

            if effective_workers <= 1:
                # Sequential path
                answer_results = []
                for i, question in enumerate(questions, 1):
                    if verbose or (i % 10 == 0):
                        print(f"    [{i}/{len(questions)}] {question.question_type}: {question.question[:60]}...")
                    answer_results.append(_eval_single(question))
            else:
                # Parallel path — each question is independent
                counter = {"done": 0}
                counter_lock = threading.Lock()
                total = len(questions)
                t_start = time.time()

                def _eval_one(question):
                    result = _eval_single(question)
                    with counter_lock:
                        counter["done"] += 1
                        n = counter["done"]
                        elapsed = time.time() - t_start
                        rate = n / elapsed if elapsed > 0 else 0
                        eta = (total - n) / rate if rate > 0 else 0
                        if verbose or (n % 50 == 0) or n == total:
                            print(f"    [{n}/{total}] {rate:.1f} q/s  ETA {eta:.0f}s")
                    return result

                answer_results = [None] * total
                with ThreadPoolExecutor(max_workers=effective_workers) as pool:
                    future_to_idx = {
                        pool.submit(_eval_one, q): i
                        for i, q in enumerate(questions)
                    }
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        answer_results[idx] = future.result()

            # Compute metrics
            overall_accuracy = compute_accuracy(answer_results)
            per_type = compute_per_type(answer_results)

            bench_result = BenchmarkResult(
                benchmark_name=benchmark_name,
                strategy_name=strategy_name,
                model_name=model_name,
                overall_accuracy=overall_accuracy,
                per_type=per_type,
                per_question=answer_results,
                ingestion_stats=ingest_stats,
            )

            print_benchmark_results(bench_result)

            if write_json:
                path = write_benchmark_json(bench_result)
                print(f"  JSON report: {path}")

            results.append(bench_result)

        finally:
            if not keep_dbs and not reuse_db:
                print(f"  Dropping eval database: {db_name}")
                drop_eval_db(admin_dsn, db_name)
            else:
                print(f"  Keeping eval database: {db_name}")

    return results


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for benchmark CLI."""
    parser = argparse.ArgumentParser(
        description="Cairn benchmark evaluation — LongMemEval and LoCoMo",
    )
    parser.add_argument(
        "benchmark",
        nargs="?",
        choices=list(BENCHMARKS.keys()),
        help=f"Benchmark to run. Available: {', '.join(BENCHMARKS.keys())}",
    )
    parser.add_argument(
        "--strategy",
        default="llm_extract",
        choices=list(STRATEGIES.keys()),
        help="Ingestion strategy (default: llm_extract)",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help=f"Embedding models. Available: {', '.join(MODEL_REGISTRY.keys())}",
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="Limit number of questions (for dev iteration)",
    )
    parser.add_argument(
        "--types",
        nargs="+",
        default=None,
        help="Filter to specific question types",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write JSON report to eval/reports/",
    )
    parser.add_argument(
        "--keep-dbs",
        action="store_true",
        help="Don't drop eval databases after evaluation",
    )
    parser.add_argument(
        "--reuse-db",
        action="store_true",
        help="Reuse existing eval database (skip create + ingest)",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip LLM enrichment during ingestion (faster, cheaper)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=10,
        help="Search result limit (default: 10)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output — show each question",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=1,
        help="Parallel workers for evaluation (default: 1, try 8-16 for Bedrock)",
    )
    parser.add_argument(
        "--scorer",
        default="llm",
        choices=["llm", "retrieval"],
        help="Scoring mode: 'llm' (LLM-as-judge, expensive) or 'retrieval' (token F1, free)",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Separate model for LLM-as-judge (e.g. hf:meta-llama/Llama-3.3-70B-Instruct). Uses main LLM if not set.",
    )
    parser.add_argument(
        "--download",
        metavar="DATASET",
        help="Download a dataset (longmemeval or locomo)",
    )
    return parser


def main(argv: list[str] | None = None):
    """CLI entry point for benchmark evaluation."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.download:
        _download_dataset(args.download)
        return

    if not args.benchmark:
        parser.print_help()
        sys.exit(1)

    run_benchmark(
        benchmark_name=args.benchmark,
        strategy_name=args.strategy,
        model_names=args.models,
        max_questions=args.max_questions,
        question_types=args.types,
        keep_dbs=args.keep_dbs,
        reuse_db=args.reuse_db,
        no_enrich=args.no_enrich,
        write_json=args.json,
        verbose=args.verbose,
        search_limit=args.k,
        workers=args.workers,
        scorer=args.scorer,
        judge_model=args.judge_model,
    )


def _download_dataset(name: str) -> None:
    """Download a benchmark dataset."""
    import subprocess
    from pathlib import Path

    data_base = Path(DATA_DIR_BASE)

    if name in ("longmemeval", "longmemeval_s", "longmemeval_l"):
        target = data_base / "longmemeval"
        target.mkdir(parents=True, exist_ok=True)
        print(f"Downloading LongMemEval to {target}...")
        print("Using huggingface-cli (install with: pip install huggingface-hub)")
        try:
            subprocess.run(
                [
                    "huggingface-cli", "download",
                    "xiaowu0162/longmemeval-cleaned",
                    "--local-dir", str(target),
                    "--repo-type", "dataset",
                ],
                check=True,
            )
            print(f"Downloaded to {target}")
        except FileNotFoundError:
            print("huggingface-cli not found. Install with: pip install huggingface-hub")
            print(f"Then run: huggingface-cli download xiaowu0162/longmemeval-cleaned --local-dir {target} --repo-type dataset")
        except subprocess.CalledProcessError as e:
            print(f"Download failed: {e}")

    elif name == "locomo":
        target = data_base / "locomo"
        target.mkdir(parents=True, exist_ok=True)
        print(f"Downloading LoCoMo to {target}...")
        print("Clone from: https://github.com/snap-research/locomo")
        print(f"Then copy locomo10.json to {target}/")
        try:
            subprocess.run(
                [
                    "curl", "-L",
                    "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json",
                    "-o", str(target / "locomo10.json"),
                ],
                check=True,
            )
            print(f"Downloaded to {target / 'locomo10.json'}")
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            print(f"Download failed: {e}")
            print(f"Manual: curl the file from GitHub and place in {target}/")
    else:
        print(f"Unknown dataset: {name}. Available: longmemeval, locomo")
        sys.exit(1)
