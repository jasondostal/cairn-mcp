"""Tests for cairn.core.audit and cairn.listeners.audit_listener."""

import json
from unittest.mock import MagicMock, call

from cairn.core.audit import AuditManager
from cairn.listeners.audit_listener import AuditListener


# ---------------------------------------------------------------------------
# AuditManager tests
# ---------------------------------------------------------------------------


class TestAuditManager:
    def _make_manager(self):
        db = MagicMock()
        return AuditManager(db), db

    def test_log_inserts_row(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {"id": 42}

        result = mgr.log(
            action="created",
            resource_type="memory",
            resource_id=7,
            project_id=1,
            trace_id="abc123",
        )

        assert result == 42
        db.execute_one.assert_called_once()
        db.commit.assert_called_once()
        sql = db.execute_one.call_args[0][0]
        assert "INSERT INTO audit_log" in sql
        assert "RETURNING id" in sql

    def test_log_passes_all_fields(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {"id": 1}

        mgr.log(
            action="updated",
            resource_type="work_item",
            resource_id=10,
            project_id=2,
            session_name="sprint-1",
            trace_id="t123",
            actor="agent-1",
            entry_point="store",
            before_state={"status": "open"},
            after_state={"status": "closed"},
            metadata={"extra": True},
        )

        params = db.execute_one.call_args[0][1]
        assert params[0] == "t123"  # trace_id
        assert params[1] == "agent-1"  # actor
        assert params[2] == "store"  # entry_point
        assert params[3] == "updated"  # action
        assert params[4] == "work_item"  # resource_type
        assert params[5] == 10  # resource_id
        # before_state and after_state are JSON strings
        assert json.loads(params[8]) == {"status": "open"}
        assert json.loads(params[9]) == {"status": "closed"}

    def test_log_none_states(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {"id": 1}

        mgr.log(action="created", resource_type="memory")

        params = db.execute_one.call_args[0][1]
        assert params[8] is None  # before_state
        assert params[9] is None  # after_state

    def test_query_no_filters(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {"total": 0}
        db.execute.return_value = []

        result = mgr.query()

        assert result["total"] == 0
        assert result["items"] == []
        assert result["limit"] == 50
        assert result["offset"] == 0

    def test_query_with_filters(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {"total": 1}
        db.execute.return_value = []

        mgr.query(
            action="created",
            resource_type="memory",
            trace_id="t123",
        )

        count_sql = db.execute_one.call_args[0][0]
        assert "a.action = %s" in count_sql
        assert "a.resource_type = %s" in count_sql
        assert "a.trace_id = %s" in count_sql

    def test_get_returns_entry(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {
            "id": 1,
            "trace_id": "t123",
            "actor": None,
            "entry_point": None,
            "action": "created",
            "resource_type": "memory",
            "resource_id": 5,
            "project": "cairn",
            "session_name": None,
            "before_state": None,
            "after_state": {"content": "test"},
            "metadata": {},
            "created_at": None,
        }

        result = mgr.get(1)
        assert result["id"] == 1
        assert result["action"] == "created"
        assert result["resource_type"] == "memory"

    def test_get_returns_none_when_missing(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = None

        result = mgr.get(999)
        assert result is None

    def test_no_update_or_delete_methods(self):
        """Immutability: AuditManager has no update or delete methods."""
        mgr, _ = self._make_manager()
        assert not hasattr(mgr, "update")
        assert not hasattr(mgr, "delete")
        assert not hasattr(mgr, "remove")


# ---------------------------------------------------------------------------
# AuditListener tests
# ---------------------------------------------------------------------------


class TestAuditListener:
    def _make_listener(self):
        audit_manager = MagicMock()
        audit_manager.log.return_value = 1
        return AuditListener(audit_manager), audit_manager

    def test_register_subscribes_to_domains(self):
        listener, _ = self._make_listener()
        bus = MagicMock()

        listener.register(bus)

        patterns = [c[0][0] for c in bus.subscribe.call_args_list]
        assert "memory.*" in patterns
        assert "work_item.*" in patterns
        assert "thinking.*" in patterns
        assert "deliverable.*" in patterns
        assert "belief.*" in patterns

    def test_handle_memory_created(self):
        listener, audit = self._make_listener()

        listener.handle({
            "event_type": "memory.created",
            "payload": {"memory_id": 42, "content": "test"},
            "project_id": 1,
            "session_name": "s1",
            "trace_id": "t123",
        })

        audit.log.assert_called_once_with(
            action="created",
            resource_type="memory",
            resource_id=42,
            project_id=1,
            session_name="s1",
            trace_id="t123",
            after_state={"memory_id": 42, "content": "test"},
        )

    def test_handle_work_item_completed(self):
        listener, audit = self._make_listener()

        listener.handle({
            "event_type": "work_item.completed",
            "payload": {"work_item_id": 10},
            "project_id": 2,
            "trace_id": "t456",
        })

        audit.log.assert_called_once()
        kw = audit.log.call_args[1]
        assert kw["action"] == "completed"
        assert kw["resource_type"] == "work_item"
        assert kw["resource_id"] == 10

    def test_handle_extracts_resource_id_from_variants(self):
        """resource_id extraction covers multiple payload key conventions."""
        listener, audit = self._make_listener()

        # deliverable_id
        listener.handle({
            "event_type": "deliverable.created",
            "payload": {"deliverable_id": 5},
        })
        assert audit.log.call_args[1]["resource_id"] == 5

        audit.reset_mock()

        # sequence_id (thinking)
        listener.handle({
            "event_type": "thinking.sequence_started",
            "payload": {"sequence_id": 99},
        })
        assert audit.log.call_args[1]["resource_id"] == 99

    def test_handle_ignores_unknown_domain(self):
        listener, audit = self._make_listener()

        listener.handle({
            "event_type": "search.executed",
            "payload": {},
        })

        audit.log.assert_not_called()

    def test_handle_ignores_malformed_event_type(self):
        listener, audit = self._make_listener()

        listener.handle({"event_type": "malformed"})
        listener.handle({"event_type": ""})
        listener.handle({})

        audit.log.assert_not_called()

    def test_handle_survives_audit_error(self):
        """Audit failures are logged but don't propagate."""
        listener, audit = self._make_listener()
        audit.log.side_effect = RuntimeError("db down")

        # Should not raise
        listener.handle({
            "event_type": "memory.created",
            "payload": {"memory_id": 1},
        })

    def test_trace_id_from_event(self):
        """trace_id comes from the event dict, not from current_trace()."""
        listener, audit = self._make_listener()

        listener.handle({
            "event_type": "memory.updated",
            "payload": {"memory_id": 7},
            "trace_id": "event-trace-123",
        })

        kw = audit.log.call_args[1]
        assert kw["trace_id"] == "event-trace-123"

    def test_handle_no_payload(self):
        """Events with no payload still get logged."""
        listener, audit = self._make_listener()

        listener.handle({
            "event_type": "work_item.completed",
        })

        audit.log.assert_called_once()
        kw = audit.log.call_args[1]
        assert kw["action"] == "completed"
        assert kw["resource_type"] == "work_item"
        assert kw["after_state"] == {}
