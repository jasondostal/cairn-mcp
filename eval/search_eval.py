"""Search quality evaluation loop.

For a given model + eval DB:
1. Load corpus, embed all memories with embed_batch()
2. Insert via raw SQL (bypasses MemoryStore.store())
3. Build {corpus_id -> db_id} mapping
4. For each query, call SearchEngine.search() in 3 modes
5. Map returned DB IDs back to corpus IDs
6. Compute all 4 metrics per query per mode
7. Aggregate: mean of each metric across all queries
"""

import logging
import time

from cairn.config import DatabaseConfig, EmbeddingConfig
from cairn.core.search import SearchEngine
from cairn.embedding.engine import EmbeddingEngine
from cairn.storage.database import Database

from eval.corpus import create_eval_db, drop_eval_db, insert_corpus, load_corpus, _replace_dbname
from eval.metrics import compute_all
from eval.queries import Query, load_queries

logger = logging.getLogger(__name__)

SEARCH_MODES = ["semantic", "keyword", "vector"]


def run_search_eval(
    admin_dsn: str,
    model_name: str,
    model_hf_id: str,
    vector_dims: int,
    k: int = 10,
    keep_db: bool = False,
) -> dict:
    """Run search quality evaluation for a single embedding model.

    Creates an eval DB, embeds corpus, runs search in all modes,
    computes metrics, and returns results.

    Returns:
        {
            "model": model_name,
            "dimensions": vector_dims,
            "embed_time_s": float,
            "modes": {
                "semantic": {"recall@k": ..., "precision@k": ..., "mrr": ..., "ndcg@k": ...},
                "keyword": {...},
                "vector": {...},
            },
            "per_query": {
                "q01": {"semantic": {...}, "keyword": {...}, "vector": {...}},
                ...
            }
        }
    """
    db_name = f"cairn_eval_{model_name}"
    eval_dsn = _replace_dbname(admin_dsn, db_name)

    # Load data
    corpus = load_corpus()
    queries = load_queries()

    # Create eval DB with correct vector dimensions
    logger.info("Creating eval DB: %s (dims=%d)", db_name, vector_dims)
    create_eval_db(admin_dsn, db_name, vector_dims)

    try:
        # Initialize embedding engine for this model
        embed_config = EmbeddingConfig(model=model_hf_id, dimensions=vector_dims)
        embedding = EmbeddingEngine(embed_config)

        # Insert corpus with embeddings
        t0 = time.time()
        id_map = insert_corpus(eval_dsn, corpus, embedding)
        embed_time = time.time() - t0
        logger.info("Corpus embedded and inserted in %.1fs", embed_time)

        # Build reverse map: db_id -> corpus_id
        reverse_map = {db_id: corpus_id for corpus_id, db_id in id_map.items()}

        # Connect search engine to eval DB
        db_config = _parse_dsn(eval_dsn)
        db = Database(db_config)
        db.connect()

        try:
            search = SearchEngine(db, embedding)

            # Evaluate each mode
            results = _evaluate_modes(search, queries, reverse_map, k)
            results["model"] = model_name
            results["dimensions"] = vector_dims
            results["embed_time_s"] = round(embed_time, 2)
            return results
        finally:
            db.close()

    finally:
        if not keep_db:
            drop_eval_db(admin_dsn, db_name)


def _evaluate_modes(
    search: SearchEngine,
    queries: list[Query],
    reverse_map: dict[int, str],
    k: int,
) -> dict:
    """Run search in all modes and compute metrics."""
    per_query = {}
    mode_aggregates = {mode: [] for mode in SEARCH_MODES}

    for query in queries:
        per_query[query.id] = {}

        for mode in SEARCH_MODES:
            # Run search
            results = search.search(
                query=query.query,
                search_mode=mode,
                limit=k,
            )

            # Map DB IDs back to corpus IDs
            retrieved = []
            for r in results:
                corpus_id = reverse_map.get(r["id"])
                if corpus_id:
                    retrieved.append(corpus_id)

            # Compute metrics
            metrics = compute_all(retrieved, query.relevant, k)
            per_query[query.id][mode] = metrics
            mode_aggregates[mode].append(metrics)

    # Aggregate: mean of each metric across all queries
    modes = {}
    for mode in SEARCH_MODES:
        if mode_aggregates[mode]:
            modes[mode] = _mean_metrics(mode_aggregates[mode])
        else:
            modes[mode] = {"recall@k": 0.0, "precision@k": 0.0, "mrr": 0.0, "ndcg@k": 0.0}

    return {"modes": modes, "per_query": per_query}


def _mean_metrics(metric_dicts: list[dict[str, float]]) -> dict[str, float]:
    """Compute the mean of each metric across a list of metric dicts."""
    if not metric_dicts:
        return {}
    keys = metric_dicts[0].keys()
    return {
        key: round(sum(d[key] for d in metric_dicts) / len(metric_dicts), 4)
        for key in keys
    }


def _parse_dsn(dsn: str) -> DatabaseConfig:
    """Parse a PostgreSQL DSN into a DatabaseConfig.

    Handles: postgresql://user:pass@host:port/dbname
    """
    # Strip protocol
    rest = dsn.replace("postgresql://", "")
    user_pass, host_rest = rest.split("@", 1)
    user, password = user_pass.split(":", 1)
    host_port, dbname = host_rest.rsplit("/", 1)

    if ":" in host_port:
        host, port_str = host_port.split(":", 1)
        port = int(port_str)
    else:
        host = host_port
        port = 5432

    return DatabaseConfig(
        host=host, port=port, name=dbname, user=user, password=password,
    )
