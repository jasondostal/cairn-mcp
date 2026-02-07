"""System health and statistics."""

from __future__ import annotations

from cairn.config import Config
from cairn.storage.database import Database


def get_status(db: Database, config: Config) -> dict:
    """Aggregate system health metrics."""
    memory_count = db.execute_one(
        "SELECT COUNT(*) as count FROM memories WHERE is_active = true"
    )
    project_count = db.execute_one("SELECT COUNT(*) as count FROM projects")
    type_counts = db.execute(
        """
        SELECT memory_type, COUNT(*) as count
        FROM memories WHERE is_active = true
        GROUP BY memory_type ORDER BY count DESC
        """
    )

    cluster_count = db.execute_one("SELECT COUNT(*) as count FROM clusters")
    last_clustering = db.execute_one(
        "SELECT created_at, cluster_count, memory_count FROM clustering_runs "
        "ORDER BY created_at DESC LIMIT 1"
    )

    clustering_info = None
    if last_clustering:
        clustering_info = {
            "last_run": last_clustering["created_at"].isoformat(),
            "clusters": last_clustering["cluster_count"],
            "memories_clustered": last_clustering["memory_count"],
        }

    return {
        "status": "healthy",
        "memories": memory_count["count"],
        "projects": project_count["count"],
        "types": {r["memory_type"]: r["count"] for r in type_counts},
        "clusters": cluster_count["count"],
        "clustering": clustering_info,
        "embedding_model": config.embedding.model,
        "embedding_dimensions": config.embedding.dimensions,
        "llm_backend": config.llm.backend,
        "llm_model": (
            config.llm.bedrock_model
            if config.llm.backend == "bedrock"
            else config.llm.ollama_model
        ),
    }
