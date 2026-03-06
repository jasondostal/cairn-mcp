"""AlertManager — rule CRUD, condition evaluation, and alert history.

Evaluates rules against metric_rollups (pre-aggregated hourly data) and
real-time health stats (ModelStats, EventBusStats). Alert delivery happens
via the webhook infrastructure (Phase 3).

Built-in templates provide common rule configs that get stored as normal rules.
"""

from __future__ import annotations

import builtins
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cairn.config import AlertingConfig
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)

# Built-in templates — convenience configs, not special execution paths.
ALERT_TEMPLATES: dict[str, dict] = {
    "error_rate_high": {
        "name": "High Error Rate",
        "condition_type": "metric_threshold",
        "condition": {
            "metric": "error_rate",
            "operator": ">",
            "threshold": 0.05,
            "window_minutes": 60,
        },
        "severity": "critical",
        "cooldown_minutes": 30,
    },
    "enrichment_failures": {
        "name": "Enrichment Failures",
        "condition_type": "metric_threshold",
        "condition": {
            "metric": "error_count",
            "operator": ">",
            "threshold": 5,
            "operation": "enrich%",
            "window_minutes": 60,
        },
        "severity": "warning",
        "cooldown_minutes": 60,
    },
    "stale_agent": {
        "name": "Stale Agent Activity",
        "condition_type": "health_status",
        "condition": {
            "component": "event_bus",
            "check": "last_event_age_minutes",
            "operator": ">",
            "threshold": 30,
        },
        "severity": "warning",
        "cooldown_minutes": 60,
    },
    "budget_exceeded": {
        "name": "Token Budget Exceeded",
        "condition_type": "metric_threshold",
        "condition": {
            "metric": "tokens_total",
            "operator": ">",
            "threshold": 1_000_000,
            "window_minutes": 1440,
        },
        "severity": "warning",
        "cooldown_minutes": 1440,
    },
}

_COMPARE_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


class AlertManager:
    """Rule CRUD + condition evaluation + alert history."""

    def __init__(self, db: Database, config: AlertingConfig):
        self.db = db
        self.config = config

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        condition_type: str,
        condition: dict,
        notification: dict | None = None,
        severity: str = "warning",
        cooldown_minutes: int = 60,
    ) -> dict:
        """Create an alert rule. Returns the created rule."""
        row = self.db.execute_one(
            """
            INSERT INTO alert_rules
                (name, condition_type, condition, notification, severity, cooldown_minutes)
            VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s)
            RETURNING id, name, condition_type, condition, notification, severity,
                      is_active, cooldown_minutes, last_fired_at, created_at, updated_at
            """,
            (
                name, condition_type,
                json.dumps(condition),
                json.dumps(notification) if notification else None,
                severity, cooldown_minutes,
            ),
        )
        assert row is not None
        self.db.commit()
        logger.info("Alert rule created: id=%d name='%s' type=%s", row["id"], name, condition_type)
        return self._row_to_dict(row)

    def get(self, rule_id: int) -> dict | None:
        """Get a single alert rule by ID."""
        row = self.db.execute_one(
            """
            SELECT id, name, condition_type, condition, notification, severity,
                   is_active, cooldown_minutes, last_fired_at, created_at, updated_at
            FROM alert_rules WHERE id = %s
            """,
            (rule_id,),
        )
        return self._row_to_dict(row) if row else None

    def list(
        self,
        *,
        is_active: bool | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List alert rules with optional filters."""
        where: list[str] = []
        params: list[Any] = []

        if is_active is not None:
            where.append("is_active = %s")
            params.append(is_active)
        if severity:
            where.append("severity = %s")
            params.append(severity)

        where_clause = " AND ".join(where) if where else "TRUE"

        count_row = self.db.execute_one(
            f"SELECT COUNT(*) as total FROM alert_rules WHERE {where_clause}",
            tuple(params),
        )
        total = count_row["total"] if count_row else 0

        query_params = list(params)
        query_params.extend([limit, offset])

        rows = self.db.execute(
            f"""
            SELECT id, name, condition_type, condition, notification, severity,
                   is_active, cooldown_minutes, last_fired_at, created_at, updated_at
            FROM alert_rules
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(query_params),
        )

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [self._row_to_dict(r) for r in rows],
        }

    def update(self, rule_id: int, **updates) -> dict | None:
        """Update alert rule fields. Returns updated rule or None."""
        allowed = {"name", "condition_type", "condition", "notification",
                    "severity", "is_active", "cooldown_minutes"}
        filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not filtered:
            return self.get(rule_id)

        set_parts = []
        params: list[Any] = []
        for key, value in filtered.items():
            if key in ("condition", "notification"):
                set_parts.append(f"{key} = %s::jsonb")
                params.append(json.dumps(value))
            else:
                set_parts.append(f"{key} = %s")
                params.append(value)

        set_parts.append("updated_at = NOW()")
        params.append(rule_id)

        row = self.db.execute_one(
            f"""
            UPDATE alert_rules
            SET {', '.join(set_parts)}
            WHERE id = %s
            RETURNING id, name, condition_type, condition, notification, severity,
                      is_active, cooldown_minutes, last_fired_at, created_at, updated_at
            """,
            tuple(params),
        )
        self.db.commit()
        return self._row_to_dict(row) if row else None

    def delete(self, rule_id: int) -> bool:
        """Delete a rule and all its history (CASCADE)."""
        row = self.db.execute_one(
            "DELETE FROM alert_rules WHERE id = %s RETURNING id",
            (rule_id,),
        )
        self.db.commit()
        if row:
            logger.info("Alert rule deleted: id=%d", rule_id)
        return row is not None

    # ------------------------------------------------------------------
    # Condition evaluation
    # ------------------------------------------------------------------

    def evaluate_rule(self, rule: dict) -> dict | None:
        """Evaluate a rule's condition. Returns {message, context, severity} or None."""
        condition_type = rule["condition_type"]
        condition = rule["condition"]

        if condition_type == "metric_threshold":
            return self._evaluate_metric_threshold(condition)
        elif condition_type == "health_status":
            return self._evaluate_health_status(condition)
        else:
            logger.warning("Unknown condition_type: %s", condition_type)
            return None

    def _evaluate_metric_threshold(self, condition: dict) -> dict | None:
        """Evaluate a metric against a threshold using metric_rollups."""
        metric = condition.get("metric", "error_rate")
        operator = condition.get("operator", ">")
        threshold = condition.get("threshold", 0)
        window_minutes = condition.get("window_minutes", 60)
        operation = condition.get("operation")
        project_id = condition.get("project_id")

        compare = _COMPARE_OPS.get(operator)
        if not compare:
            logger.warning("Unknown operator: %s", operator)
            return None

        # Build WHERE clause for metric_rollups query
        where_parts = ["bucket_hour >= NOW() - make_interval(mins => %s)"]
        params: list[Any] = [window_minutes]

        if operation:
            where_parts.append("operation LIKE %s")
            params.append(operation)
        if project_id is not None:
            where_parts.append("project_id = %s")
            params.append(project_id)

        where_clause = " AND ".join(where_parts)

        row = self.db.execute_one(
            f"""
            SELECT COALESCE(SUM(op_count), 0) as total_ops,
                   COALESCE(SUM(error_count), 0) as total_errors,
                   COALESCE(SUM(tokens_in_sum + tokens_out_sum), 0) as tokens_total,
                   AVG(latency_p50) as avg_p50,
                   AVG(latency_p95) as avg_p95,
                   AVG(latency_p99) as avg_p99
            FROM metric_rollups
            WHERE {where_clause}
            """,
            tuple(params),
        )
        self.db.rollback()  # read-only query, release connection

        if not row:
            return None

        total_ops = row["total_ops"] or 0
        total_errors = row["total_errors"] or 0
        tokens_total = row["tokens_total"] or 0

        # Compute derived metrics
        metrics = {
            "op_count": total_ops,
            "error_count": total_errors,
            "error_rate": (total_errors / total_ops) if total_ops > 0 else 0.0,
            "tokens_total": tokens_total,
            "avg_p50": row["avg_p50"],
            "avg_p95": row["avg_p95"],
            "avg_p99": row["avg_p99"],
        }

        actual_value = metrics.get(metric)
        if actual_value is None:
            logger.warning("Unknown metric: %s", metric)
            return None

        if compare(actual_value, threshold):
            return {
                "message": f"{metric} = {actual_value:.4f} {operator} {threshold} (window: {window_minutes}m)",
                "context": {
                    "metric": metric,
                    "value": actual_value,
                    "threshold": threshold,
                    "operator": operator,
                    "window_minutes": window_minutes,
                    "rollup_snapshot": {k: v for k, v in metrics.items() if v is not None},
                },
            }
        return None

    def _evaluate_health_status(self, condition: dict) -> dict | None:
        """Evaluate real-time health from in-memory stats singletons."""
        from cairn.core.stats import embedding_stats, event_bus_stats, llm_stats

        component = condition.get("component", "")
        check = condition.get("check", "health")
        operator = condition.get("operator", "==")
        threshold = condition.get("threshold")

        compare = _COMPARE_OPS.get(operator)
        if not compare:
            return None

        # Resolve component to stats object
        stats_map = {
            "embedding": embedding_stats,
            "llm": llm_stats,
            "event_bus": event_bus_stats,
        }
        stats = stats_map.get(component)
        if stats is None:
            logger.warning("Unknown health component: %s", component)
            return None

        if check == "health":
            # Compare health string: threshold is e.g. "unhealthy"
            actual = stats.health
            if compare(actual, threshold):
                return {
                    "message": f"{component}.health = '{actual}' {operator} '{threshold}'",
                    "context": {
                        "component": component,
                        "health": actual,
                        "full_stats": stats.to_dict(),
                    },
                }
        elif check == "last_event_age_minutes":
            # Only for event_bus — minutes since last event
            if not hasattr(stats, '_last_event_at'):
                return None
            last_event = getattr(stats, '_last_event_at', None)
            if last_event is None:
                age_minutes = float('inf')
            else:
                age_minutes = (datetime.now(UTC) - last_event).total_seconds() / 60.0
            if compare(age_minutes, threshold):
                return {
                    "message": f"{component}.last_event_age = {age_minutes:.1f}m {operator} {threshold}m",
                    "context": {
                        "component": component,
                        "check": check,
                        "age_minutes": round(age_minutes, 1),
                        "threshold": threshold,
                    },
                }
        elif check == "error_count":
            error_count = getattr(stats, '_errors', 0)
            if compare(error_count, threshold):
                return {
                    "message": f"{component}.errors = {error_count} {operator} {threshold}",
                    "context": {
                        "component": component,
                        "check": check,
                        "error_count": error_count,
                        "threshold": threshold,
                    },
                }

        return None

    # ------------------------------------------------------------------
    # Alert history
    # ------------------------------------------------------------------

    def record_alert(
        self,
        *,
        rule_id: int,
        severity: str,
        message: str,
        context: dict | None = None,
        delivered: bool = False,
    ) -> int:
        """Record an alert firing. Updates last_fired_at on the rule. Returns history ID."""
        row = self.db.execute_one(
            """
            INSERT INTO alert_history (rule_id, severity, message, context, delivered)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            RETURNING id
            """,
            (rule_id, severity, message, json.dumps(context or {}), delivered),
        )
        assert row is not None
        # Update last_fired_at on the rule
        self.db.execute(
            "UPDATE alert_rules SET last_fired_at = NOW() WHERE id = %s",
            (rule_id,),
        )
        self.db.commit()
        logger.info(
            "Alert fired: rule_id=%d severity=%s delivered=%s msg='%s'",
            rule_id, severity, delivered, message[:100],
        )
        return row["id"]

    def query_history(
        self,
        *,
        rule_id: int | None = None,
        severity: str | None = None,
        days: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Query alert history with filters."""
        where: list[str] = []
        params: list[Any] = []

        if rule_id is not None:
            where.append("ah.rule_id = %s")
            params.append(rule_id)
        if severity:
            where.append("ah.severity = %s")
            params.append(severity)
        if days:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            where.append("ah.created_at >= %s")
            params.append(cutoff)

        where_clause = " AND ".join(where) if where else "TRUE"

        count_row = self.db.execute_one(
            f"SELECT COUNT(*) as total FROM alert_history ah WHERE {where_clause}",
            tuple(params),
        )
        total = count_row["total"] if count_row else 0

        query_params = list(params)
        query_params.extend([limit, offset])

        rows = self.db.execute(
            f"""
            SELECT ah.id, ah.rule_id, ah.severity, ah.message, ah.context,
                   ah.delivered, ah.created_at, ar.name as rule_name
            FROM alert_history ah
            JOIN alert_rules ar ON ah.rule_id = ar.id
            WHERE {where_clause}
            ORDER BY ah.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(query_params),
        )

        items = [
            {
                "id": r["id"],
                "rule_id": r["rule_id"],
                "rule_name": r["rule_name"],
                "severity": r["severity"],
                "message": r["message"],
                "context": r["context"],
                "delivered": r["delivered"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def active_alerts(self, *, hours: int = 24) -> builtins.list[dict]:
        """Recent alerts grouped by rule, within the given time window."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        rows = self.db.execute(
            """
            SELECT ah.id, ah.rule_id, ah.severity, ah.message, ah.context,
                   ah.delivered, ah.created_at, ar.name as rule_name
            FROM alert_history ah
            JOIN alert_rules ar ON ah.rule_id = ar.id
            WHERE ah.created_at >= %s
            ORDER BY ah.created_at DESC
            """,
            (cutoff,),
        )
        return [
            {
                "id": r["id"],
                "rule_id": r["rule_id"],
                "rule_name": r["rule_name"],
                "severity": r["severity"],
                "message": r["message"],
                "context": r["context"],
                "delivered": r["delivered"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "condition_type": row["condition_type"],
            "condition": row["condition"] or {},
            "notification": row["notification"] or {},
            "severity": row["severity"],
            "is_active": row["is_active"],
            "cooldown_minutes": row["cooldown_minutes"],
            "last_fired_at": row["last_fired_at"].isoformat() if row["last_fired_at"] else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
