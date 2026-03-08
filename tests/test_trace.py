"""Tests for cairn.core.trace — TraceContext propagation, child spans, integration."""

import threading
from unittest.mock import MagicMock

from cairn.core.trace import (
    TraceContext,
    new_trace,
    child_span,
    current_trace,
    clear_trace,
    set_trace_project,
    set_trace_tool,
    set_trace_model,
)
from cairn.core.analytics import UsageEvent, track_operation


class TestTraceContext:
    def test_new_trace_sets_contextvar(self):
        clear_trace()
        ctx = new_trace(actor="mcp", entry_point="store")
        assert current_trace() is ctx
        clear_trace()

    def test_trace_id_format(self):
        clear_trace()
        ctx = new_trace()
        assert len(ctx.trace_id) == 32
        assert len(ctx.span_id) == 16
        # Valid hex
        int(ctx.trace_id, 16)
        int(ctx.span_id, 16)
        clear_trace()

    def test_new_trace_defaults(self):
        clear_trace()
        ctx = new_trace()
        assert ctx.actor == "mcp"
        assert ctx.entry_point == ""
        assert ctx.parent_span_id is None
        clear_trace()

    def test_new_trace_custom_actor(self):
        clear_trace()
        ctx = new_trace(actor="rest", entry_point="/api/status")
        assert ctx.actor == "rest"
        assert ctx.entry_point == "/api/status"
        clear_trace()

    def test_child_span_shares_trace_id(self):
        clear_trace()
        parent = new_trace(actor="mcp", entry_point="store")
        child = child_span(entry_point="enrichment")
        assert child.trace_id == parent.trace_id
        assert child.span_id != parent.span_id
        assert len(child.span_id) == 16
        clear_trace()

    def test_child_span_links_parent(self):
        clear_trace()
        parent = new_trace()
        child = child_span()
        assert child.parent_span_id == parent.span_id
        clear_trace()

    def test_child_span_inherits_actor(self):
        clear_trace()
        new_trace(actor="rest", entry_point="/api/store")
        child = child_span(entry_point="enrichment")
        assert child.actor == "rest"
        clear_trace()

    def test_child_span_without_parent_creates_root(self):
        clear_trace()
        ctx = child_span(entry_point="orphan")
        assert ctx.parent_span_id is None
        assert ctx.entry_point == "orphan"
        assert current_trace() is ctx
        clear_trace()

    def test_clear_trace(self):
        new_trace()
        assert current_trace() is not None
        clear_trace()
        assert current_trace() is None

    def test_current_trace_none_by_default(self):
        clear_trace()
        assert current_trace() is None

    def test_attribution_fields_mutable(self):
        """Attribution fields (project, tool_name, model) are mutable by design (ca-231)."""
        ctx = TraceContext(trace_id="a" * 32, span_id="b" * 16)
        assert ctx.project is None
        assert ctx.tool_name is None
        assert ctx.model is None
        ctx.project = "my-project"
        ctx.tool_name = "store"
        ctx.model = "claude-4"
        assert ctx.project == "my-project"
        assert ctx.tool_name == "store"
        assert ctx.model == "claude-4"

    def test_thread_isolation(self):
        clear_trace()
        new_trace(actor="main")
        result = {}

        def check_in_thread():
            result["trace"] = current_trace()

        t = threading.Thread(target=check_in_thread)
        t.start()
        t.join()
        assert result["trace"] is None
        assert current_trace() is not None  # main thread still has it
        clear_trace()

    def test_unique_ids(self):
        clear_trace()
        ctx1 = new_trace()
        id1 = ctx1.trace_id
        clear_trace()
        ctx2 = new_trace()
        assert ctx2.trace_id != id1
        clear_trace()

    def test_set_trace_project(self):
        clear_trace()
        new_trace()
        set_trace_project("cairn")
        assert current_trace().project == "cairn"
        clear_trace()

    def test_set_trace_tool(self):
        clear_trace()
        new_trace()
        set_trace_tool("store")
        assert current_trace().tool_name == "store"
        clear_trace()

    def test_set_trace_model(self):
        clear_trace()
        new_trace()
        set_trace_model("claude-4")
        assert current_trace().model == "claude-4"
        clear_trace()

    def test_set_trace_noop_without_trace(self):
        """Setters are no-ops when no trace is active."""
        clear_trace()
        set_trace_project("cairn")
        set_trace_tool("store")
        set_trace_model("claude-4")
        assert current_trace() is None

    def test_child_span_inherits_attribution(self):
        clear_trace()
        new_trace()
        set_trace_project("cairn")
        set_trace_tool("store")
        set_trace_model("claude-4")
        child = child_span(entry_point="enrichment")
        assert child.project == "cairn"
        assert child.tool_name == "store"
        assert child.model == "claude-4"
        clear_trace()


class TestTrackOperationTrace:
    def test_creates_trace_when_none_exists(self):
        clear_trace()
        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value=None)

        @track_operation("test_store", tracker=tracker)
        def my_func():
            return {"result": "ok"}

        my_func()
        event = tracker.track.call_args[0][0]
        assert event.trace_id is not None
        assert len(event.trace_id) == 32
        assert event.span_id is not None
        assert len(event.span_id) == 16
        assert event.parent_span_id is None
        # Should have cleared after
        assert current_trace() is None

    def test_uses_existing_trace(self):
        clear_trace()
        parent = new_trace(actor="rest", entry_point="/api/store")

        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value=None)

        @track_operation("test_store", tracker=tracker)
        def my_func():
            return {"result": "ok"}

        my_func()
        event = tracker.track.call_args[0][0]
        assert event.trace_id == parent.trace_id
        # Should NOT have cleared (REST middleware's trace)
        assert current_trace() is not None
        assert current_trace().trace_id == parent.trace_id
        clear_trace()

    def test_clears_only_when_created(self):
        clear_trace()
        existing = new_trace(actor="rest", entry_point="/api/search")

        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value=None)

        @track_operation("test_search", tracker=tracker)
        def my_func():
            return {"result": "ok"}

        my_func()
        # Trace still alive — we didn't create it
        assert current_trace() is existing
        clear_trace()

    def test_trace_survives_exception(self):
        clear_trace()
        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value=None)

        @track_operation("test_fail", tracker=tracker)
        def my_func():
            raise ValueError("boom")

        try:
            my_func()
        except ValueError:
            pass

        event = tracker.track.call_args[0][0]
        assert event.trace_id is not None
        assert event.success is False
        assert current_trace() is None  # created internally, so cleared

    def test_no_tracker_no_trace(self):
        """When analytics tracker is None, trace context is not touched."""
        clear_trace()

        @track_operation("test_noop", tracker=None)
        def my_func():
            return {"ok": True}

        my_func()
        # No trace created when tracker is None
        assert current_trace() is None

    def test_trace_attribution_flows_to_event(self):
        """track_operation reads project/model/tool from trace context (ca-231)."""
        clear_trace()
        ctx = new_trace(actor="mcp", entry_point="store")
        ctx.project = "my-project"
        ctx.tool_name = "store"
        ctx.model = "claude-4"

        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value={"id": 42})

        @track_operation("test_store", tracker=tracker)
        def my_func():
            return {"result": "ok"}

        my_func()
        event = tracker.track.call_args[0][0]
        assert event.project_id == 42  # resolved from "my-project"
        assert event.model == "claude-4"
        assert event.tool_name == "store"
        clear_trace()

    def test_explicit_project_overrides_trace(self):
        """Explicit project kwarg takes priority over trace context."""
        clear_trace()
        ctx = new_trace(actor="mcp", entry_point="store")
        ctx.project = "trace-project"

        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value={"id": 99})

        @track_operation("test_store", tracker=tracker)
        def my_func(project=None):
            return {"result": "ok"}

        my_func(project="explicit-project")
        event = tracker.track.call_args[0][0]
        # project_id should be resolved from "explicit-project", not "trace-project"
        call_args = tracker.db.execute_one.call_args
        assert call_args[0][1] == ("explicit-project",)
        clear_trace()
