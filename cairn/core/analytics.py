"""Analytics — usage tracking, rollup aggregation, and query engine."""

from __future__ import annotations

import functools
import inspect
import logging
import math
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cairn.config import AnalyticsConfig
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)

# Module-level tracker singleton (set once during service init)
_analytics_tracker: UsageTracker | None = None


def init_analytics_tracker(tracker: UsageTracker | None) -> None:
    """Set the module-level analytics tracker. Called once from services.py."""
    global _analytics_tracker
    _analytics_tracker = tracker


# ============================================================
# Data model
# ============================================================

@dataclass
class UsageEvent:
    """Single MCP tool invocation record."""
    operation: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    project_id: int | None = None
    session_name: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    model: str | None = None
    success: bool = True
    error_message: str | None = None
    metadata: dict | None = None


# ============================================================
# UsageTracker — non-blocking async writer
# ============================================================

class UsageTracker:
    """Thread-safe, non-blocking usage event writer.

    Events are enqueued and flushed to the database in batches
    by a background thread. If the queue is full, events are
    silently dropped (acceptable for telemetry).
    """

    QUEUE_MAX = 10_000
    FLUSH_INTERVAL = 5.0  # seconds

    def __init__(self, db: Database):
        self.db = db
        self._queue: queue.Queue[UsageEvent] = queue.Queue(maxsize=self.QUEUE_MAX)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def track(self, event: UsageEvent) -> None:
        """Enqueue an event. Non-blocking; drops silently if queue full."""
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass  # telemetry loss is acceptable

    def start(self) -> None:
        """Start the background flush thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="UsageTracker",
        )
        self._thread.start()
        logger.info("UsageTracker: started")

    def stop(self) -> None:
        """Signal stop and wait for final flush."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.warning("UsageTracker: thread did not stop within timeout")
        else:
            logger.info("UsageTracker: stopped")
        self._thread = None

    def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            self._flush_batch()
            self._stop_event.wait(timeout=self.FLUSH_INTERVAL)
        # Final drain on shutdown
        self._flush_batch()

    def _flush_batch(self) -> None:
        batch: list[UsageEvent] = []
        while len(batch) < 500:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if not batch:
            return

        try:
            for ev in batch:
                self.db.execute(
                    """
                    INSERT INTO usage_events
                        (timestamp, operation, project_id, session_name,
                         tokens_in, tokens_out, latency_ms, model,
                         success, error_message, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        ev.timestamp, ev.operation, ev.project_id, ev.session_name,
                        ev.tokens_in, ev.tokens_out, ev.latency_ms, ev.model,
                        ev.success, ev.error_message,
                        __import__("json").dumps(ev.metadata) if ev.metadata else "{}",
                    ),
                )
            self.db.commit()
        except Exception:
            logger.warning("UsageTracker: flush failed for %d events", len(batch), exc_info=True)


# ============================================================
# track_operation — decorator for core service methods
# ============================================================

_SENTINEL = object()


def track_operation(operation_name: str, tracker: UsageTracker | None = _SENTINEL):
    """Decorator that records operation invocations as UsageEvents.

    Applied to core service methods so all transports (MCP, REST, CLI)
    are tracked. Uses the module-level _analytics_tracker singleton
    unless an explicit tracker is passed (useful for tests).

    At decoration time, inspects the function signature to find the
    index of 'project' and 'session_name' parameters so they can be
    extracted from positional args at call time.
    """
    def decorator(func):
        # Pre-compute parameter positions at decoration time (O(1) at call time)
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())
        project_idx = param_names.index("project") if "project" in param_names else None
        session_idx = param_names.index("session_name") if "session_name" in param_names else None

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Resolve which tracker to use
            active_tracker = tracker if tracker is not _SENTINEL else _analytics_tracker
            if active_tracker is None:
                return func(*args, **kwargs)

            t0 = time.monotonic()
            success = True
            error_msg = None

            try:
                result = func(*args, **kwargs)
                if isinstance(result, dict) and "error" in result:
                    success = False
                    error_msg = str(result["error"])[:512]
                return result
            except Exception as exc:
                success = False
                error_msg = str(exc)[:512]
                raise
            finally:
                latency_ms = (time.monotonic() - t0) * 1000

                # Extract project/session from args or kwargs
                project_name = kwargs.get("project")
                if project_name is None and project_idx is not None and project_idx < len(args):
                    val = args[project_idx]
                    if isinstance(val, str):
                        project_name = val

                session_name = kwargs.get("session_name")
                if session_name is None and session_idx is not None and session_idx < len(args):
                    val = args[session_idx]
                    if isinstance(val, str):
                        session_name = val

                # Resolve project_id from project name
                project_id = None
                if project_name:
                    try:
                        row = active_tracker.db.execute_one(
                            "SELECT id FROM projects WHERE name = %s", (project_name,),
                        )
                        if row:
                            project_id = row["id"]
                    except Exception:
                        pass  # best-effort

                active_tracker.track(UsageEvent(
                    operation=operation_name,
                    project_id=project_id,
                    session_name=session_name,
                    latency_ms=latency_ms,
                    success=success,
                    error_message=error_msg,
                ))

        return wrapper
    return decorator


# ============================================================
# RollupWorker — background aggregation
# ============================================================

class RollupWorker:
    """Background thread that aggregates raw usage_events into hourly metric_rollups.

    Same lifecycle pattern as DigestWorker: daemon thread, stop event,
    exponential backoff on errors.
    """

    POLL_INTERVAL = 60.0
    BATCH_SIZE = 500
    MAX_BACKOFF = 300.0

    def __init__(self, db: Database, *, retention_days: int = 90):
        self.db = db
        self.retention_days = retention_days
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="RollupWorker",
        )
        self._thread.start()
        logger.info("RollupWorker: started (retention=%dd)", self.retention_days)

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.warning("RollupWorker: thread did not stop within timeout")
        else:
            logger.info("RollupWorker: stopped")
        self._thread = None

    def _run_loop(self) -> None:
        poll_interval = self.POLL_INTERVAL

        while not self._stop_event.is_set():
            try:
                processed = self._process_batch()
                if processed:
                    poll_interval = self.POLL_INTERVAL
                else:
                    self._stop_event.wait(timeout=poll_interval)
            except Exception:
                logger.warning("RollupWorker: error in cycle, backing off", exc_info=True)
                poll_interval = min(poll_interval * 3, self.MAX_BACKOFF)
                self._stop_event.wait(timeout=poll_interval)

        # Final run on shutdown
        try:
            self._process_batch()
        except Exception:
            pass

    def _process_batch(self) -> bool:
        """Read raw events above watermark, aggregate, upsert rollups.

        Returns True if events were processed.
        """
        # Get current watermark
        state = self.db.execute_one("SELECT last_event_id FROM rollup_state WHERE id = 1")
        if not state:
            return False
        watermark = state["last_event_id"]

        # Fetch batch of raw events above watermark
        rows = self.db.execute(
            """
            SELECT id, timestamp, operation, project_id,
                   tokens_in, tokens_out, latency_ms, success
            FROM usage_events
            WHERE id > %s
            ORDER BY id ASC
            LIMIT %s
            """,
            (watermark, self.BATCH_SIZE),
        )

        if not rows:
            # Run retention cleanup periodically even when idle
            self._cleanup_old_events()
            return False

        # Group by (bucket_hour, operation, project_id)
        buckets: dict[tuple, list[dict]] = {}
        max_id = watermark
        for row in rows:
            ts = row["timestamp"]
            bucket_hour = ts.replace(minute=0, second=0, microsecond=0)
            key = (bucket_hour, row["operation"], row["project_id"])
            buckets.setdefault(key, []).append(row)
            if row["id"] > max_id:
                max_id = row["id"]

        # Upsert each bucket
        for (bucket_hour, operation, project_id), events in buckets.items():
            op_count = len(events)
            error_count = sum(1 for e in events if not e["success"])
            tokens_in_sum = sum(e["tokens_in"] for e in events)
            tokens_out_sum = sum(e["tokens_out"] for e in events)

            # Calculate latency percentiles
            latencies = sorted(e["latency_ms"] for e in events)
            p50 = self._percentile(latencies, 50)
            p95 = self._percentile(latencies, 95)
            p99 = self._percentile(latencies, 99)

            coalesce_pid = project_id if project_id is not None else 0

            self.db.execute(
                """
                INSERT INTO metric_rollups
                    (bucket_hour, operation, project_id,
                     op_count, error_count, tokens_in_sum, tokens_out_sum,
                     latency_p50, latency_p95, latency_p99)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (bucket_hour, operation, COALESCE(project_id, 0))
                DO UPDATE SET
                    op_count = metric_rollups.op_count + EXCLUDED.op_count,
                    error_count = metric_rollups.error_count + EXCLUDED.error_count,
                    tokens_in_sum = metric_rollups.tokens_in_sum + EXCLUDED.tokens_in_sum,
                    tokens_out_sum = metric_rollups.tokens_out_sum + EXCLUDED.tokens_out_sum,
                    latency_p50 = EXCLUDED.latency_p50,
                    latency_p95 = EXCLUDED.latency_p95,
                    latency_p99 = EXCLUDED.latency_p99
                """,
                (
                    bucket_hour, operation, project_id,
                    op_count, error_count, tokens_in_sum, tokens_out_sum,
                    p50, p95, p99,
                ),
            )

        # Advance watermark
        self.db.execute(
            "UPDATE rollup_state SET last_event_id = %s, updated_at = now() WHERE id = 1",
            (max_id,),
        )
        self.db.commit()

        logger.info("RollupWorker: processed %d events into %d buckets", len(rows), len(buckets))
        return True

    def _cleanup_old_events(self) -> None:
        """Delete raw events older than retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        self.db.execute(
            "DELETE FROM usage_events WHERE timestamp < %s", (cutoff,),
        )
        self.db.commit()

    @staticmethod
    def _percentile(sorted_values: list[float], pct: int) -> float | None:
        if not sorted_values:
            return None
        n = len(sorted_values)
        k = (pct / 100) * (n - 1)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_values[f]
        return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


# ============================================================
# AnalyticsQueryEngine — read-only query layer
# ============================================================

class AnalyticsQueryEngine:
    """Read-only query layer for analytics dashboards."""

    def __init__(self, db: Database, *, analytics_config: AnalyticsConfig | None = None):
        self.db = db
        self._config = analytics_config

    def overview(self, days: int = 7) -> dict:
        """KPI values + sparkline arrays."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Totals from raw events
        totals = self.db.execute_one(
            """
            SELECT
                COUNT(*) as total_ops,
                COALESCE(SUM(tokens_in + tokens_out), 0) as total_tokens,
                AVG(latency_ms) as avg_latency,
                COUNT(*) FILTER (WHERE NOT success) as error_count
            FROM usage_events
            WHERE timestamp >= %s
            """,
            (cutoff,),
        )

        total_ops = totals["total_ops"] if totals else 0
        total_tokens = totals["total_tokens"] if totals else 0
        avg_latency = round(totals["avg_latency"] or 0, 1) if totals else 0
        error_count = totals["error_count"] if totals else 0
        error_rate = round((error_count / total_ops * 100) if total_ops > 0 else 0, 2)

        # Sparkline: hourly for <=7d, daily for longer
        if days <= 7:
            sparkline = self._hourly_sparkline(cutoff)
        else:
            sparkline = self._daily_sparkline(cutoff)

        return {
            "kpis": {
                "operations": {"value": total_ops, "label": "Operations"},
                "tokens": {"value": total_tokens, "label": "Tokens"},
                "avg_latency": {"value": avg_latency, "label": "Avg Latency (ms)"},
                "error_rate": {"value": error_rate, "label": "Error Rate (%)"},
            },
            "sparklines": sparkline,
            "days": days,
        }

    def timeseries(
        self, days: int = 7, granularity: str = "hour",
        project: str | None = None, operation: str | None = None,
    ) -> dict:
        """Time series of operations, tokens, errors."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        if granularity == "hour":
            trunc = "hour"
        else:
            trunc = "day"

        where = ["timestamp >= %s"]
        params: list[Any] = [cutoff]

        if project:
            where.append("project_id = (SELECT id FROM projects WHERE name = %s)")
            params.append(project)
        if operation:
            where.append("operation = %s")
            params.append(operation)

        where_clause = " AND ".join(where)

        rows = self.db.execute(
            f"""
            SELECT
                date_trunc('{trunc}', timestamp) as bucket,
                COUNT(*) as operations,
                COALESCE(SUM(tokens_in), 0) as tokens_in,
                COALESCE(SUM(tokens_out), 0) as tokens_out,
                COUNT(*) FILTER (WHERE NOT success) as errors
            FROM usage_events
            WHERE {where_clause}
            GROUP BY bucket
            ORDER BY bucket ASC
            """,
            tuple(params),
        )

        series = [
            {
                "timestamp": r["bucket"].isoformat(),
                "operations": r["operations"],
                "tokens_in": r["tokens_in"],
                "tokens_out": r["tokens_out"],
                "errors": r["errors"],
            }
            for r in rows
        ]

        return {"series": series, "granularity": granularity, "days": days}

    def operations(
        self, days: int = 7, project: str | None = None,
        operation: str | None = None, success: bool | None = None,
        limit: int = 50, offset: int = 0,
    ) -> dict:
        """Raw event log with pagination."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        where = ["ue.timestamp >= %s"]
        params: list[Any] = [cutoff]

        if project:
            where.append("p.name = %s")
            params.append(project)
        if operation:
            where.append("ue.operation = %s")
            params.append(operation)
        if success is not None:
            where.append("ue.success = %s")
            params.append(success)

        where_clause = " AND ".join(where)

        count_row = self.db.execute_one(
            f"""
            SELECT COUNT(*) as total
            FROM usage_events ue
            LEFT JOIN projects p ON ue.project_id = p.id
            WHERE {where_clause}
            """,
            tuple(params),
        )
        total = count_row["total"] if count_row else 0

        query_params = list(params)
        query_params.extend([limit, offset])

        rows = self.db.execute(
            f"""
            SELECT ue.id, ue.timestamp, ue.operation, ue.tokens_in, ue.tokens_out,
                   ue.latency_ms, ue.model, ue.success, ue.error_message,
                   ue.session_name, p.name as project
            FROM usage_events ue
            LEFT JOIN projects p ON ue.project_id = p.id
            WHERE {where_clause}
            ORDER BY ue.timestamp DESC
            LIMIT %s OFFSET %s
            """,
            tuple(query_params),
        )

        items = [
            {
                "id": r["id"],
                "timestamp": r["timestamp"].isoformat(),
                "operation": r["operation"],
                "project": r["project"],
                "tokens_in": r["tokens_in"],
                "tokens_out": r["tokens_out"],
                "latency_ms": round(r["latency_ms"], 1),
                "model": r["model"],
                "success": r["success"],
                "error_message": r["error_message"],
                "session_name": r["session_name"],
            }
            for r in rows
        ]

        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def projects_breakdown(self, days: int = 7) -> dict:
        """Per-project stats with trend direction."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        prev_cutoff = cutoff - timedelta(days=days)

        # Current period
        current = self.db.execute(
            """
            SELECT p.name as project,
                   COUNT(*) as ops,
                   COALESCE(SUM(ue.tokens_in + ue.tokens_out), 0) as tokens,
                   AVG(ue.latency_ms) as avg_latency,
                   COUNT(*) FILTER (WHERE NOT ue.success) as errors
            FROM usage_events ue
            LEFT JOIN projects p ON ue.project_id = p.id
            WHERE ue.timestamp >= %s
            GROUP BY p.name
            ORDER BY ops DESC
            """,
            (cutoff,),
        )

        # Previous period for trend
        previous = self.db.execute(
            """
            SELECT p.name as project, COUNT(*) as ops
            FROM usage_events ue
            LEFT JOIN projects p ON ue.project_id = p.id
            WHERE ue.timestamp >= %s AND ue.timestamp < %s
            GROUP BY p.name
            """,
            (prev_cutoff, cutoff),
        )
        prev_map = {r["project"]: r["ops"] for r in previous}

        items = []
        for r in current:
            proj = r["project"] or "Unassigned"
            prev_ops = prev_map.get(r["project"], 0)
            curr_ops = r["ops"]

            if prev_ops == 0:
                trend = "up" if curr_ops > 0 else "flat"
            elif curr_ops > prev_ops * 1.1:
                trend = "up"
            elif curr_ops < prev_ops * 0.9:
                trend = "down"
            else:
                trend = "flat"

            items.append({
                "project": proj,
                "operations": curr_ops,
                "tokens": r["tokens"],
                "avg_latency": round(r["avg_latency"] or 0, 1),
                "errors": r["errors"],
                "error_rate": round((r["errors"] / curr_ops * 100) if curr_ops > 0 else 0, 2),
                "trend": trend,
            })

        return {"items": items, "days": days}

    def models_performance(self, days: int = 7) -> dict:
        """Per-model latency percentiles, error rates, token totals."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        rows = self.db.execute(
            """
            SELECT
                COALESCE(model, 'System') as model,
                COUNT(*) as calls,
                COALESCE(SUM(tokens_in), 0) as tokens_in,
                COALESCE(SUM(tokens_out), 0) as tokens_out,
                COUNT(*) FILTER (WHERE NOT success) as errors,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) as p99
            FROM usage_events
            WHERE timestamp >= %s
            GROUP BY COALESCE(model, 'System')
            ORDER BY calls DESC
            """,
            (cutoff,),
        )

        items = [
            {
                "model": r["model"],
                "calls": r["calls"],
                "tokens_in": r["tokens_in"],
                "tokens_out": r["tokens_out"],
                "errors": r["errors"],
                "error_rate": round((r["errors"] / r["calls"] * 100) if r["calls"] > 0 else 0, 2),
                "latency_p50": round(r["p50"] or 0, 1),
                "latency_p95": round(r["p95"] or 0, 1),
                "latency_p99": round(r["p99"] or 0, 1),
            }
            for r in rows
        ]

        return {"items": items, "days": days}

    def get_summary(self) -> dict:
        """Quick summary for the status endpoint."""
        total_row = self.db.execute_one(
            "SELECT COUNT(*) as cnt FROM usage_events", (),
        )
        state_row = self.db.execute_one(
            "SELECT last_event_id, updated_at FROM rollup_state WHERE id = 1", (),
        )

        return {
            "total_events": total_row["cnt"] if total_row else 0,
            "rollup_watermark": state_row["last_event_id"] if state_row else 0,
            "rollup_updated_at": state_row["updated_at"].isoformat() if state_row and state_row["updated_at"] else None,
        }

    def memory_type_growth(self, days: int = 90, granularity: str = "day") -> dict:
        """Cumulative memory counts by type per time bucket. Stacked area chart data."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        trunc = "day" if granularity == "day" else "hour"

        rows = self.db.execute(
            f"""
            SELECT
                date_trunc('{trunc}', created_at) as bucket,
                memory_type,
                COUNT(*) as cnt
            FROM memories
            WHERE is_active = true AND created_at >= %s
            GROUP BY bucket, memory_type
            ORDER BY bucket ASC
            """,
            (cutoff,),
        )

        # Build cumulative series: {bucket -> {type -> cumulative_count}}
        type_totals: dict[str, int] = {}
        buckets: dict[str, dict[str, int]] = {}
        for row in rows:
            bucket_key = row["bucket"].isoformat()
            mt = row["memory_type"]
            type_totals[mt] = type_totals.get(mt, 0) + row["cnt"]
            if bucket_key not in buckets:
                buckets[bucket_key] = {}
            buckets[bucket_key][mt] = type_totals[mt]

        # Fill forward — each bucket carries forward previous totals for types not seen
        all_types = sorted(type_totals.keys())
        running: dict[str, int] = {t: 0 for t in all_types}
        series = []
        for bucket_key in sorted(buckets.keys()):
            for t in all_types:
                if t in buckets[bucket_key]:
                    running[t] = buckets[bucket_key][t]
            point = {"timestamp": bucket_key, **{t: running[t] for t in all_types}}
            series.append(point)

        return {"series": series, "types": all_types, "days": days, "granularity": granularity}

    def entity_counts_sparkline(self, days: int = 30) -> dict:
        """Daily creation counts for memories, projects, cairns, clusters. KPI sparkline data."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        def _daily_counts(table: str, ts_col: str) -> list[dict]:
            rows = self.db.execute(
                f"""
                SELECT date_trunc('day', {ts_col}) as bucket, COUNT(*) as cnt
                FROM {table}
                WHERE {ts_col} >= %s
                GROUP BY bucket ORDER BY bucket ASC
                """,
                (cutoff,),
            )
            return [{"t": r["bucket"].isoformat(), "v": r["cnt"]} for r in rows]

        # Current totals
        totals = self.db.execute_one(
            """
            SELECT
                (SELECT COUNT(*) FROM memories WHERE is_active = true) as memories,
                (SELECT COUNT(*) FROM projects) as projects,
                (SELECT COUNT(*) FROM cairns WHERE set_at IS NOT NULL) as cairns,
                (SELECT COUNT(*) FROM clusters) as clusters
            """,
            (),
        )

        return {
            "totals": {
                "memories": totals["memories"] if totals else 0,
                "projects": totals["projects"] if totals else 0,
                "cairns": totals["cairns"] if totals else 0,
                "clusters": totals["clusters"] if totals else 0,
            },
            "sparklines": {
                "memories": _daily_counts("memories", "created_at"),
                "projects": _daily_counts("projects", "created_at"),
                "cairns": _daily_counts("cairns", "set_at"),
                "clusters": _daily_counts("clusters", "created_at"),
            },
            "days": days,
        }

    def activity_heatmap(self, days: int = 365) -> dict:
        """Daily operation counts from usage_events. Pre-aggregated heatmap data."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        rows = self.db.execute(
            """
            SELECT date_trunc('day', timestamp) as bucket, COUNT(*) as cnt
            FROM usage_events
            WHERE timestamp >= %s
            GROUP BY bucket ORDER BY bucket ASC
            """,
            (cutoff,),
        )

        day_list = [
            {"date": r["bucket"].strftime("%Y-%m-%d"), "count": r["cnt"]}
            for r in rows
        ]

        return {"days": day_list}

    # --- internal helpers ---

    def _hourly_sparkline(self, cutoff: datetime) -> dict:
        rows = self.db.execute(
            """
            SELECT date_trunc('hour', timestamp) as bucket,
                   COUNT(*) as ops,
                   COALESCE(SUM(tokens_in + tokens_out), 0) as tokens,
                   COUNT(*) FILTER (WHERE NOT success) as errors
            FROM usage_events
            WHERE timestamp >= %s
            GROUP BY bucket ORDER BY bucket ASC
            """,
            (cutoff,),
        )
        return {
            "operations": [{"t": r["bucket"].isoformat(), "v": r["ops"]} for r in rows],
            "tokens": [{"t": r["bucket"].isoformat(), "v": r["tokens"]} for r in rows],
            "errors": [{"t": r["bucket"].isoformat(), "v": r["errors"]} for r in rows],
        }

    def _daily_sparkline(self, cutoff: datetime) -> dict:
        rows = self.db.execute(
            """
            SELECT date_trunc('day', timestamp) as bucket,
                   COUNT(*) as ops,
                   COALESCE(SUM(tokens_in + tokens_out), 0) as tokens,
                   COUNT(*) FILTER (WHERE NOT success) as errors
            FROM usage_events
            WHERE timestamp >= %s
            GROUP BY bucket ORDER BY bucket ASC
            """,
            (cutoff,),
        )
        return {
            "operations": [{"t": r["bucket"].isoformat(), "v": r["ops"]} for r in rows],
            "tokens": [{"t": r["bucket"].isoformat(), "v": r["tokens"]} for r in rows],
            "errors": [{"t": r["bucket"].isoformat(), "v": r["errors"]} for r in rows],
        }
