"""System health and statistics."""

from __future__ import annotations

from cairn import __version__
from cairn.config import EXPERIMENTAL_CAPABILITIES, Config
from cairn.core import stats
from cairn.core.analytics import track_operation
from cairn.storage.database import Database


@track_operation("status")
def get_status(db: Database, config: Config, graph_provider=None) -> dict:
    """Aggregate system health metrics."""
    subsystem_errors: list[str] = []

    # DB reachability check
    try:
        db.execute_one("SELECT 1 AS ok")
    except Exception:
        subsystem_errors.append("database")

    memory_count_row = db.execute_one(
        "SELECT COUNT(*) as count FROM memories WHERE is_active = true"
    )
    assert memory_count_row is not None
    memory_count = memory_count_row
    project_count_row = db.execute_one("SELECT COUNT(*) as count FROM projects")
    assert project_count_row is not None
    project_count = project_count_row
    type_counts = db.execute(
        """
        SELECT memory_type, COUNT(*) as count
        FROM memories WHERE is_active = true
        GROUP BY memory_type ORDER BY count DESC
        """
    )

    cluster_count_row = db.execute_one("SELECT COUNT(*) as count FROM clusters")
    assert cluster_count_row is not None
    cluster_count = cluster_count_row
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

    # Model observability
    models = {}
    if stats.embedding_stats:
        models["embedding"] = stats.embedding_stats.to_dict()
    if stats.llm_stats:
        models["llm"] = stats.llm_stats.to_dict()

    # Event bus observability
    event_bus_info = None
    if stats.event_bus_stats:
        eb = stats.event_bus_stats.to_dict()
        # Enrich with DB-sourced totals (lifetime, not just since restart)
        try:
            total_events = db.execute_one("SELECT COUNT(*) as cnt FROM events")
            active_sessions = db.execute_one(
                "SELECT COUNT(*) as cnt FROM sessions WHERE closed_at IS NULL"
            )
            total_sessions = db.execute_one("SELECT COUNT(*) as cnt FROM sessions")
            eb["db"] = {
                "total_events": total_events["cnt"] if total_events else 0,
                "active_sessions": active_sessions["cnt"] if active_sessions else 0,
                "total_sessions": total_sessions["cnt"] if total_sessions else 0,
            }
        except Exception:
            pass  # tables may not exist yet
        event_bus_info = eb

    status = "degraded" if subsystem_errors else "healthy"

    result = {
        "version": __version__,
        "status": status,
        "profile": config.profile or None,
        "memories": memory_count["count"],
        "projects": project_count["count"],
        "types": {r["memory_type"]: r["count"] for r in type_counts},
        "clusters": cluster_count["count"],
        "clustering": clustering_info,
        "models": models,
        "event_bus": event_bus_info,
        "llm_capabilities": config.capabilities.active_list(),
        "experimental_capabilities": sorted(
            c for c in config.capabilities.active_list()
            if c in EXPERIMENTAL_CAPABILITIES
        ),
    }

    # Analytics summary
    try:
        analytics_row = db.execute_one(
            "SELECT COUNT(*) as cnt FROM usage_events", (),
        )
        state_row = db.execute_one(
            "SELECT last_event_id, updated_at FROM rollup_state WHERE id = 1", (),
        )
        if analytics_row:
            result["analytics"] = {
                "total_events": analytics_row["cnt"],
                "rollup_watermark": state_row["last_event_id"] if state_row else 0,
                "rollup_updated_at": state_row["updated_at"].isoformat() if state_row and state_row["updated_at"] else None,
            }
    except Exception:
        pass  # tables may not exist yet (pre-migration)

    result["graph_backend"] = "neo4j" if graph_provider else None

    if subsystem_errors:
        result["subsystem_errors"] = subsystem_errors

    return result
