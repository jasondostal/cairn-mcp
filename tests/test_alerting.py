"""Tests for Watchtower Phase 4: Health Alerting."""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from cairn.config import AlertingConfig
from cairn.core.alerting import AlertManager, ALERT_TEMPLATES, _COMPARE_OPS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config():
    return AlertingConfig(enabled=True, eval_interval_seconds=60)


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def mgr(db, config):
    return AlertManager(db, config)


# ---------------------------------------------------------------------------
# Compare operators
# ---------------------------------------------------------------------------

class TestCompareOps:
    def test_greater_than(self):
        assert _COMPARE_OPS[">"](5, 3) is True
        assert _COMPARE_OPS[">"](3, 5) is False

    def test_less_than(self):
        assert _COMPARE_OPS["<"](3, 5) is True
        assert _COMPARE_OPS["<"](5, 3) is False

    def test_equals(self):
        assert _COMPARE_OPS["=="](5, 5) is True
        assert _COMPARE_OPS["=="]("healthy", "healthy") is True
        assert _COMPARE_OPS["=="]("healthy", "unhealthy") is False

    def test_not_equals(self):
        assert _COMPARE_OPS["!="](5, 3) is True
        assert _COMPARE_OPS["!="]("degraded", "healthy") is True

    def test_gte_lte(self):
        assert _COMPARE_OPS[">="](5, 5) is True
        assert _COMPARE_OPS[">="](6, 5) is True
        assert _COMPARE_OPS["<="](5, 5) is True
        assert _COMPARE_OPS["<="](4, 5) is True


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class TestAlertManagerCRUD:
    def test_create(self, mgr, db):
        db.execute_one.return_value = {
            "id": 1, "name": "test", "condition_type": "metric_threshold",
            "condition": {"metric": "error_rate", "operator": ">", "threshold": 0.05},
            "notification": None, "severity": "warning", "is_active": True,
            "cooldown_minutes": 60, "last_fired_at": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        result = mgr.create(
            name="test",
            condition_type="metric_threshold",
            condition={"metric": "error_rate", "operator": ">", "threshold": 0.05},
        )

        assert result["id"] == 1
        assert result["name"] == "test"
        assert result["condition_type"] == "metric_threshold"
        db.execute_one.assert_called_once()
        db.commit.assert_called_once()

    def test_get(self, mgr, db):
        db.execute_one.return_value = {
            "id": 1, "name": "test", "condition_type": "metric_threshold",
            "condition": {"metric": "error_rate"}, "notification": None,
            "severity": "warning", "is_active": True, "cooldown_minutes": 60,
            "last_fired_at": None, "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        result = mgr.get(1)
        assert result["id"] == 1

    def test_get_not_found(self, mgr, db):
        db.execute_one.return_value = None
        assert mgr.get(999) is None

    def test_list(self, mgr, db):
        db.execute_one.return_value = {"total": 2}
        db.execute.return_value = [
            {"id": 1, "name": "r1", "condition_type": "metric_threshold",
             "condition": {}, "notification": None, "severity": "warning",
             "is_active": True, "cooldown_minutes": 60, "last_fired_at": None,
             "created_at": datetime.now(timezone.utc),
             "updated_at": datetime.now(timezone.utc)},
            {"id": 2, "name": "r2", "condition_type": "health_status",
             "condition": {}, "notification": None, "severity": "critical",
             "is_active": True, "cooldown_minutes": 30, "last_fired_at": None,
             "created_at": datetime.now(timezone.utc),
             "updated_at": datetime.now(timezone.utc)},
        ]
        result = mgr.list()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    def test_update(self, mgr, db):
        db.execute_one.return_value = {
            "id": 1, "name": "updated", "condition_type": "metric_threshold",
            "condition": {}, "notification": None, "severity": "critical",
            "is_active": True, "cooldown_minutes": 30, "last_fired_at": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        result = mgr.update(1, name="updated", severity="critical")
        assert result["name"] == "updated"
        assert result["severity"] == "critical"
        db.commit.assert_called_once()

    def test_update_jsonb_fields(self, mgr, db):
        """condition and notification should be serialized as JSONB."""
        db.execute_one.return_value = {
            "id": 1, "name": "test", "condition_type": "metric_threshold",
            "condition": {"metric": "op_count"}, "notification": {"webhook_id": 5},
            "severity": "warning", "is_active": True, "cooldown_minutes": 60,
            "last_fired_at": None, "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mgr.update(1, condition={"metric": "op_count"}, notification={"webhook_id": 5})
        call_args = db.execute_one.call_args
        sql = call_args[0][0]
        assert "::jsonb" in sql

    def test_delete(self, mgr, db):
        db.execute_one.return_value = {"id": 1}
        assert mgr.delete(1) is True
        db.commit.assert_called_once()

    def test_delete_not_found(self, mgr, db):
        db.execute_one.return_value = None
        assert mgr.delete(999) is False


# ---------------------------------------------------------------------------
# Metric threshold evaluation
# ---------------------------------------------------------------------------

class TestMetricThreshold:
    def test_error_rate_above_threshold(self, mgr, db):
        # Setup: error_rate = 100/1000 = 0.10 > 0.05
        db.execute_one.return_value = {
            "total_ops": 1000, "total_errors": 100, "tokens_total": 50000,
            "avg_p50": 120.0, "avg_p95": 450.0, "avg_p99": 900.0,
        }
        result = mgr._evaluate_metric_threshold({
            "metric": "error_rate", "operator": ">", "threshold": 0.05,
            "window_minutes": 60,
        })
        assert result is not None
        assert "error_rate" in result["message"]
        assert result["context"]["value"] == pytest.approx(0.1)

    def test_error_rate_below_threshold(self, mgr, db):
        # error_rate = 10/1000 = 0.01 < 0.05
        db.execute_one.return_value = {
            "total_ops": 1000, "total_errors": 10, "tokens_total": 50000,
            "avg_p50": 120.0, "avg_p95": 450.0, "avg_p99": 900.0,
        }
        result = mgr._evaluate_metric_threshold({
            "metric": "error_rate", "operator": ">", "threshold": 0.05,
            "window_minutes": 60,
        })
        assert result is None

    def test_zero_ops_no_division_error(self, mgr, db):
        db.execute_one.return_value = {
            "total_ops": 0, "total_errors": 0, "tokens_total": 0,
            "avg_p50": None, "avg_p95": None, "avg_p99": None,
        }
        result = mgr._evaluate_metric_threshold({
            "metric": "error_rate", "operator": ">", "threshold": 0.05,
            "window_minutes": 60,
        })
        # error_rate = 0.0, not > 0.05
        assert result is None

    def test_tokens_total_exceeded(self, mgr, db):
        db.execute_one.return_value = {
            "total_ops": 500, "total_errors": 0, "tokens_total": 2_000_000,
            "avg_p50": 100.0, "avg_p95": 200.0, "avg_p99": 300.0,
        }
        result = mgr._evaluate_metric_threshold({
            "metric": "tokens_total", "operator": ">", "threshold": 1_000_000,
            "window_minutes": 1440,
        })
        assert result is not None
        assert result["context"]["value"] == 2_000_000

    def test_operation_filter(self, mgr, db):
        """Operation filter should appear as LIKE in the query."""
        db.execute_one.return_value = {
            "total_ops": 100, "total_errors": 10, "tokens_total": 1000,
            "avg_p50": None, "avg_p95": None, "avg_p99": None,
        }
        mgr._evaluate_metric_threshold({
            "metric": "error_count", "operator": ">", "threshold": 5,
            "operation": "enrich%", "window_minutes": 60,
        })
        call_args = db.execute_one.call_args
        params = call_args[0][1]
        assert "enrich%" in params

    def test_unknown_metric(self, mgr, db):
        db.execute_one.return_value = {
            "total_ops": 100, "total_errors": 0, "tokens_total": 0,
            "avg_p50": None, "avg_p95": None, "avg_p99": None,
        }
        result = mgr._evaluate_metric_threshold({
            "metric": "nonexistent_metric", "operator": ">", "threshold": 0,
            "window_minutes": 60,
        })
        assert result is None

    def test_unknown_operator(self, mgr, db):
        result = mgr._evaluate_metric_threshold({
            "metric": "error_rate", "operator": "~=", "threshold": 0.05,
            "window_minutes": 60,
        })
        assert result is None


# ---------------------------------------------------------------------------
# Health status evaluation
# ---------------------------------------------------------------------------

class TestHealthStatus:
    @patch("cairn.core.stats.embedding_stats")
    @patch("cairn.core.stats.llm_stats")
    @patch("cairn.core.stats.event_bus_stats")
    def test_embedding_unhealthy(self, mock_ebs, mock_llm, mock_emb, mgr):
        mock_emb.health = "unhealthy"
        mock_emb.to_dict.return_value = {"health": "unhealthy"}

        result = mgr._evaluate_health_status({
            "component": "embedding", "check": "health",
            "operator": "==", "threshold": "unhealthy",
        })
        assert result is not None
        assert "embedding" in result["message"]

    @patch("cairn.core.stats.embedding_stats")
    @patch("cairn.core.stats.llm_stats")
    @patch("cairn.core.stats.event_bus_stats")
    def test_embedding_healthy_no_alert(self, mock_ebs, mock_llm, mock_emb, mgr):
        mock_emb.health = "healthy"

        result = mgr._evaluate_health_status({
            "component": "embedding", "check": "health",
            "operator": "==", "threshold": "unhealthy",
        })
        assert result is None

    @patch("cairn.core.stats.embedding_stats")
    @patch("cairn.core.stats.llm_stats")
    @patch("cairn.core.stats.event_bus_stats")
    def test_stale_event_bus(self, mock_ebs, mock_llm, mock_emb, mgr):
        mock_ebs._last_event_at = datetime.now(timezone.utc) - timedelta(minutes=60)

        result = mgr._evaluate_health_status({
            "component": "event_bus", "check": "last_event_age_minutes",
            "operator": ">", "threshold": 30,
        })
        assert result is not None
        assert result["context"]["age_minutes"] > 30

    @patch("cairn.core.stats.embedding_stats")
    @patch("cairn.core.stats.llm_stats")
    @patch("cairn.core.stats.event_bus_stats")
    def test_recent_event_bus_no_alert(self, mock_ebs, mock_llm, mock_emb, mgr):
        mock_ebs._last_event_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        result = mgr._evaluate_health_status({
            "component": "event_bus", "check": "last_event_age_minutes",
            "operator": ">", "threshold": 30,
        })
        assert result is None

    def test_unknown_component(self, mgr):
        result = mgr._evaluate_health_status({
            "component": "nonexistent", "check": "health",
            "operator": "==", "threshold": "unhealthy",
        })
        assert result is None


# ---------------------------------------------------------------------------
# Alert history
# ---------------------------------------------------------------------------

class TestAlertHistory:
    def test_record_alert(self, mgr, db):
        db.execute_one.return_value = {"id": 42}
        history_id = mgr.record_alert(
            rule_id=1, severity="critical",
            message="error_rate = 0.10 > 0.05",
            context={"metric": "error_rate", "value": 0.10},
            delivered=True,
        )
        assert history_id == 42
        # Should have 2 DB calls: INSERT + UPDATE last_fired_at
        assert db.execute_one.call_count == 1
        assert db.execute.call_count == 1
        db.commit.assert_called_once()

    def test_query_history(self, mgr, db):
        db.execute_one.return_value = {"total": 1}
        db.execute.return_value = [
            {"id": 1, "rule_id": 1, "rule_name": "test", "severity": "warning",
             "message": "test msg", "context": {}, "delivered": False,
             "created_at": datetime.now(timezone.utc)},
        ]
        result = mgr.query_history(severity="warning")
        assert result["total"] == 1
        assert result["items"][0]["rule_name"] == "test"

    def test_active_alerts(self, mgr, db):
        db.execute.return_value = [
            {"id": 1, "rule_id": 1, "rule_name": "r1", "severity": "critical",
             "message": "msg", "context": {}, "delivered": True,
             "created_at": datetime.now(timezone.utc)},
        ]
        alerts = mgr.active_alerts(hours=24)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "critical"


# ---------------------------------------------------------------------------
# Evaluate rule dispatch
# ---------------------------------------------------------------------------

class TestEvaluateRule:
    def test_dispatches_metric_threshold(self, mgr, db):
        db.execute_one.return_value = {
            "total_ops": 100, "total_errors": 20, "tokens_total": 1000,
            "avg_p50": None, "avg_p95": None, "avg_p99": None,
        }
        rule = {
            "id": 1, "condition_type": "metric_threshold",
            "condition": {"metric": "error_rate", "operator": ">", "threshold": 0.05,
                          "window_minutes": 60},
        }
        result = mgr.evaluate_rule(rule)
        assert result is not None

    def test_unknown_condition_type(self, mgr):
        rule = {"id": 1, "condition_type": "magic", "condition": {}}
        result = mgr.evaluate_rule(rule)
        assert result is None


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

class TestTemplates:
    def test_all_templates_have_required_fields(self):
        for key, tmpl in ALERT_TEMPLATES.items():
            assert "name" in tmpl, f"Template {key} missing name"
            assert "condition_type" in tmpl, f"Template {key} missing condition_type"
            assert "condition" in tmpl, f"Template {key} missing condition"
            assert "severity" in tmpl, f"Template {key} missing severity"
            assert "cooldown_minutes" in tmpl, f"Template {key} missing cooldown_minutes"

    def test_error_rate_high_template(self):
        tmpl = ALERT_TEMPLATES["error_rate_high"]
        assert tmpl["condition_type"] == "metric_threshold"
        assert tmpl["condition"]["metric"] == "error_rate"
        assert tmpl["severity"] == "critical"

    def test_budget_exceeded_template(self):
        tmpl = ALERT_TEMPLATES["budget_exceeded"]
        assert tmpl["condition"]["metric"] == "tokens_total"
        assert tmpl["condition"]["threshold"] == 1_000_000

    def test_template_count(self):
        assert len(ALERT_TEMPLATES) == 4


# ---------------------------------------------------------------------------
# AlertEvaluator (worker)
# ---------------------------------------------------------------------------

class TestAlertEvaluator:
    def test_poll_skips_when_no_rules(self, db, config):
        from cairn.core.alert_worker import AlertEvaluator
        alert_mgr = MagicMock()
        worker = AlertEvaluator(db, alert_mgr, None, config)

        db.execute.return_value = []
        worker._poll()
        db.rollback.assert_called_once()
        alert_mgr.evaluate_rule.assert_not_called()

    def test_poll_evaluates_and_records(self, db, config):
        from cairn.core.alert_worker import AlertEvaluator
        alert_mgr = MagicMock()
        alert_mgr.evaluate_rule.return_value = {
            "message": "test alert", "context": {"value": 0.1},
        }
        alert_mgr.record_alert.return_value = 1

        now = datetime.now(timezone.utc)
        db.execute.return_value = [
            {"id": 1, "name": "r1", "condition_type": "metric_threshold",
             "condition": {}, "notification": None, "severity": "warning",
             "is_active": True, "cooldown_minutes": 60, "last_fired_at": None,
             "created_at": now, "updated_at": now},
        ]

        worker = AlertEvaluator(db, alert_mgr, None, config)
        worker._poll()

        alert_mgr.evaluate_rule.assert_called_once()
        alert_mgr.record_alert.assert_called_once()
        record_kwargs = alert_mgr.record_alert.call_args.kwargs
        assert record_kwargs["severity"] == "warning"
        assert record_kwargs["delivered"] is False

    def test_poll_fires_webhook_when_configured(self, db, config):
        from cairn.core.alert_worker import AlertEvaluator
        alert_mgr = MagicMock()
        alert_mgr.evaluate_rule.return_value = {
            "message": "test alert", "context": {},
        }
        alert_mgr.record_alert.return_value = 1

        webhook_mgr = MagicMock()
        webhook_mgr.create_delivery.return_value = 99

        now = datetime.now(timezone.utc)
        db.execute.return_value = [
            {"id": 1, "name": "r1", "condition_type": "metric_threshold",
             "condition": {}, "notification": {"webhook_id": 5},
             "severity": "critical", "is_active": True, "cooldown_minutes": 60,
             "last_fired_at": None, "created_at": now, "updated_at": now},
        ]

        worker = AlertEvaluator(db, alert_mgr, webhook_mgr, config)
        worker._poll()

        webhook_mgr.create_delivery.assert_called_once()
        delivery_kwargs = webhook_mgr.create_delivery.call_args.kwargs
        assert delivery_kwargs["webhook_id"] == 5
        assert delivery_kwargs["request_body"]["severity"] == "critical"

        record_kwargs = alert_mgr.record_alert.call_args.kwargs
        assert record_kwargs["delivered"] is True

    def test_poll_resilient_to_evaluation_error(self, db, config):
        from cairn.core.alert_worker import AlertEvaluator
        alert_mgr = MagicMock()
        alert_mgr.evaluate_rule.side_effect = RuntimeError("boom")

        now = datetime.now(timezone.utc)
        db.execute.return_value = [
            {"id": 1, "name": "r1", "condition_type": "metric_threshold",
             "condition": {}, "notification": None, "severity": "warning",
             "is_active": True, "cooldown_minutes": 60, "last_fired_at": None,
             "created_at": now, "updated_at": now},
        ]

        worker = AlertEvaluator(db, alert_mgr, None, config)
        # Should not raise
        worker._poll()
        alert_mgr.record_alert.assert_not_called()

    def test_start_stop_lifecycle(self, db, config):
        from cairn.core.alert_worker import AlertEvaluator
        alert_mgr = MagicMock()
        worker = AlertEvaluator(db, alert_mgr, None, config)

        worker.start()
        assert worker._thread is not None
        assert worker._thread.is_alive()

        worker.stop()
        assert worker._thread is None
