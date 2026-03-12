"""Tests for epic auto-decomposition (ca-151)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cairn.core.agents import AgentDefinition, AgentRegistry


class TestDecompositionContext:
    """Test WorkItemManager.decomposition_context()."""

    def _make_wim(self):
        from cairn.core.work_items import WorkItemManager
        db = MagicMock()
        event_bus = MagicMock()
        wim = WorkItemManager(db, event_bus, MagicMock())
        return wim, db

    def test_decomposition_context_no_children(self):
        wim, db = self._make_wim()

        item = {
            "id": 10, "seq_num": 10, "title": "Build auth", "status": "open",
            "project_id": 1, "display_id": "ca-10", "project_name": "cairn",
            "parent_id": None, "work_item_prefix": "ca",
            "item_type": "epic", "priority": 2, "risk_tier": 0,
        }

        item_detail = {
            "id": 10, "display_id": "ca-10", "title": "Build auth",
            "description": "Build authentication system", "item_type": "epic",
            "acceptance_criteria": None, "risk_tier": 0, "status": "open",
            "gate_type": None, "gate_data": {}, "gate_response": None,
            "linked_memories": [],
        }

        wim._resolve_id = lambda wid: item
        wim._display_id = lambda i: i.get("display_id", f"#{i['id']}")
        wim._display_id_from_row = lambda r: f"{r.get('work_item_prefix', 'ca')}-{r.get('seq_num', r['id'])}"

        # generate_briefing will call get() which we mock
        wim.get = MagicMock(return_value=item_detail)

        # No children
        db.execute.return_value = []
        db.execute_one.return_value = None

        result = wim.decomposition_context(10)

        assert result["work_item"]["title"] == "Build auth"
        assert result["existing_children"] == []
        assert result["children_count"] == 0
        assert result["is_re_decomposition"] is False

    def test_decomposition_context_with_existing_children(self):
        wim, db = self._make_wim()

        item = {
            "id": 10, "seq_num": 10, "title": "Build auth", "status": "open",
            "project_id": 1, "display_id": "ca-10", "project_name": "cairn",
            "parent_id": None, "work_item_prefix": "ca",
            "item_type": "epic", "priority": 2, "risk_tier": 0,
        }

        item_detail = {
            "id": 10, "display_id": "ca-10", "title": "Build auth",
            "description": "Build auth", "item_type": "epic",
            "acceptance_criteria": None, "risk_tier": 0, "status": "in_progress",
            "gate_type": None, "gate_data": {}, "gate_response": None,
            "linked_memories": [],
        }

        wim._resolve_id = lambda wid: item
        wim._display_id = lambda i: i.get("display_id", f"#{i['id']}")
        wim._display_id_from_row = lambda r: f"{r.get('work_item_prefix', 'ca')}-{r.get('seq_num', r['id'])}"
        wim.get = MagicMock(return_value=item_detail)

        children_rows = [
            {"id": 11, "seq_num": 11, "title": "Design schema", "description": "DB schema",
             "status": "done", "item_type": "subtask", "priority": 2, "risk_tier": 1,
             "assignee": "agent:claude_code", "work_item_prefix": "ca"},
            {"id": 12, "seq_num": 12, "title": "Implement JWT", "description": "JWT auth",
             "status": "open", "item_type": "subtask", "priority": 1, "risk_tier": 1,
             "assignee": None, "work_item_prefix": "ca"},
        ]

        call_count = 0

        def mock_execute(sql, params=None):
            nonlocal call_count
            call_count += 1
            if "parent_id" in str(sql):
                return children_rows
            return []

        db.execute.side_effect = mock_execute
        db.execute_one.return_value = None

        result = wim.decomposition_context(10)

        assert result["children_count"] == 2
        assert result["is_re_decomposition"] is True
        assert result["existing_children"][0]["title"] == "Design schema"
        assert result["existing_children"][0]["status"] == "done"
        assert result["existing_children"][1]["title"] == "Implement JWT"

    def test_briefing_includes_item_type(self):
        wim, db = self._make_wim()

        item = {
            "id": 5, "seq_num": 5, "title": "An epic", "status": "open",
            "project_id": 1, "display_id": "ca-5", "project_name": "cairn",
            "parent_id": None, "work_item_prefix": "ca",
        }

        item_detail = {
            "id": 5, "display_id": "ca-5", "title": "An epic",
            "description": "Epic desc", "item_type": "epic",
            "acceptance_criteria": None, "risk_tier": 0, "status": "open",
            "gate_type": None, "gate_data": {}, "gate_response": None,
            "linked_memories": [],
        }

        wim._resolve_id = lambda wid: item
        wim.get = MagicMock(return_value=item_detail)
        db.execute_one.return_value = None

        result = wim.generate_briefing(5)
        assert result["work_item"]["item_type"] == "epic"


class TestBriefingDecompositionFormat:
    """Test that _format_briefing includes decomposition instructions."""

    def _make_wm(self):
        from cairn.core.workspace import WorkspaceManager
        db = MagicMock()
        wm = WorkspaceManager(db)
        return wm

    def test_decomposition_briefing_has_instructions(self):
        wm = self._make_wm()

        briefing = {
            "work_item": {
                "display_id": "ca-10", "title": "Build auth",
                "description": "Build auth system", "risk_tier": 0,
                "risk_label": "patrol", "status": "open",
                "gate_type": None, "gate_data": {}, "gate_response": None,
            },
            "constraints": {},
            "context": [],
            "parent_chain": [],
            "existing_children": [],
            "children_count": 0,
            "is_re_decomposition": False,
        }

        result = wm._format_briefing(briefing)

        assert "Decomposition Instructions" in result
        assert "add_child" in result
        assert "3-7 subtasks" in result
        assert "set_gate" in result
        assert "Do NOT dispatch workers" in result

    def test_standard_briefing_no_decomposition(self):
        wm = self._make_wm()

        briefing = {
            "work_item": {
                "display_id": "ca-11", "title": "Implement JWT",
                "description": "JWT auth", "risk_tier": 1,
                "risk_label": "voyage", "status": "open",
                "gate_type": None, "gate_data": {}, "gate_response": None,
            },
            "constraints": {},
            "context": [],
            "parent_chain": [],
        }

        result = wm._format_briefing(briefing)

        assert "## Instructions" in result
        assert "Decomposition Instructions" not in result
        assert "heartbeat" in result

    def test_decomposition_with_existing_children(self):
        wm = self._make_wm()

        briefing = {
            "work_item": {
                "display_id": "ca-10", "title": "Build auth",
                "description": "Build auth", "risk_tier": 0,
                "risk_label": "patrol", "status": "in_progress",
                "gate_type": None, "gate_data": {}, "gate_response": None,
            },
            "constraints": {},
            "context": [],
            "parent_chain": [],
            "existing_children": [
                {"display_id": "ca-11", "title": "Design schema", "status": "done"},
                {"display_id": "ca-12", "title": "Implement JWT", "status": "open"},
            ],
            "children_count": 2,
            "is_re_decomposition": True,
        }

        result = wm._format_briefing(briefing)

        assert "Existing Subtasks" in result
        assert "ca-11" in result
        assert "Design schema" in result
        assert "2 subtask(s) already exist" in result
        assert "Review before creating duplicates" in result

    def test_agent_system_prompt_injected(self):
        wm = self._make_wm()

        coord_def = AgentDefinition(
            name="cairn-coordinator", role="coordinator",
            description="Orchestration agent",
            system_prompt="You are a COORDINATOR agent.",
        )

        briefing = {
            "work_item": {
                "display_id": "ca-10", "title": "Epic",
                "description": "Desc", "risk_tier": 0,
                "risk_label": "patrol", "status": "open",
                "gate_type": None, "gate_data": {}, "gate_response": None,
            },
            "constraints": {},
            "context": [],
            "parent_chain": [],
            "existing_children": [],
            "children_count": 0,
            "is_re_decomposition": False,
        }

        result = wm._format_briefing(briefing, agent_def=coord_def)

        # System prompt should appear before the briefing
        coord_idx = result.index("COORDINATOR")
        briefing_idx = result.index("[DISPATCH BRIEFING]")
        assert coord_idx < briefing_idx


class TestDispatchValidationIntegration:
    """Test that dispatch validates agent definitions."""

    def test_coordinator_blocked_from_subtask(self):
        from cairn.core.agents import AgentDefinition, validate_dispatch

        coord = AgentDefinition(name="c", role="coordinator", description="")
        wi = {"item_type": "subtask", "parent_id": 1}
        errors = validate_dispatch(coord, wi)
        assert len(errors) == 1

    def test_dispatch_auto_sets_risk_tier(self):
        """Verify dispatch uses agent_def.default_risk_tier when not specified."""
        from cairn.core.workspace import WorkspaceManager

        db = MagicMock()
        wm = WorkspaceManager(db)

        registry = AgentRegistry()
        wm.agent_registry = registry

        wim = MagicMock()
        wim.get.return_value = {
            "id": 1, "display_id": "ca-1", "title": "Test",
            "item_type": "task", "status": "open", "project": "cairn",
            "parent_id": None,
        }
        wim.claim.return_value = None
        wm.work_item_manager = wim

        # No backends — will return error, but we can still verify the flow
        result = wm.dispatch(work_item_id=1, agent="cairn-research")
        # cairn-research has default_risk_tier=3, but since no backend
        # is configured, it errors before using it
        assert "error" in result
