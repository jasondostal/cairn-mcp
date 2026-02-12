"""Multi-model orchestrator and model registry.

Runs search eval for each registered model, collects results,
and enables side-by-side comparison. Extensible by adding entries
to MODEL_REGISTRY.
"""

import logging

from eval.search_eval import run_search_eval

logger = logging.getLogger(__name__)

MODEL_REGISTRY = {
    "minilm": {
        "hf_id": "all-MiniLM-L6-v2",
        "dimensions": 384,
        "backend": "local",
    },
    "mpnet": {
        "hf_id": "all-mpnet-base-v2",
        "dimensions": 768,
        "backend": "local",
    },
    "titan_v2": {
        "hf_id": "amazon.titan-embed-text-v2:0",
        "dimensions": 1024,
        "backend": "bedrock",
    },
}


def run_model_comparison(
    admin_dsn: str,
    model_names: list[str] | None = None,
    k: int = 10,
    keep_dbs: bool = False,
) -> list[dict]:
    """Run search eval for each selected model and return all results.

    Args:
        admin_dsn: PostgreSQL admin DSN (connects to 'postgres' database).
        model_names: List of model keys from MODEL_REGISTRY. None = all.
        k: Number of results to evaluate.
        keep_dbs: If True, don't drop eval databases after evaluation.

    Returns:
        List of result dicts, one per model.
    """
    if model_names is None:
        model_names = list(MODEL_REGISTRY.keys())

    results = []
    for name in model_names:
        if name not in MODEL_REGISTRY:
            logger.warning("Unknown model: %s, skipping", name)
            continue

        spec = MODEL_REGISTRY[name]
        logger.info(
            "Evaluating model: %s (%s, %d-dim)",
            name, spec["hf_id"], spec["dimensions"],
        )

        try:
            result = run_search_eval(
                admin_dsn=admin_dsn,
                model_name=name,
                model_hf_id=spec["hf_id"],
                vector_dims=spec["dimensions"],
                k=k,
                keep_db=keep_dbs,
            )
            results.append(result)
            logger.info("Model %s completed", name)
        except Exception:
            logger.exception("Model %s failed", name)

    return results
