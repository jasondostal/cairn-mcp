"""Tests for agent persistent memory — compound learning (ca-158)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from cairn.core.agent_memory import AgentMemoryStore


def _make_store():
    db = MagicMock()
    store = AgentMemoryStore(db)
    return store, db


class TestStoreLearning:
    """Test learning storage."""

    def test_store_basic(self):
        store, db = _make_store()
        db.execute_one.return_value = {"id": 1, "created_at": datetime.now(timezone.utc)}
        with patch("cairn.core.agent_memory.get_or_create_project", return_value=10):
            result = store.store_learning("agent-1", "proj", "Use pytest fixtures")

        assert result["id"] == 1
        assert result["agent_name"] == "agent-1"
        assert result["project"] == "proj"
        assert result["stored"] is True
        db.commit.assert_called_once()

    def test_store_with_work_item(self):
        store, db = _make_store()
        db.execute_one.return_value = {"id": 2, "created_at": datetime.now(timezone.utc)}
        with patch("cairn.core.agent_memory.get_or_create_project", return_value=10):
            result = store.store_learning(
                "agent-1", "proj", "Always run tests first",
                work_item_id="ca-42", learning_type="convention", importance=0.9,
            )

        assert result["id"] == 2
        assert result["learning_type"] == "convention"
        # Verify the SQL params include work_item_id
        call_args = db.execute_one.call_args
        assert "ca-42" in call_args[0][1]

    def test_store_default_importance(self):
        store, db = _make_store()
        db.execute_one.return_value = {"id": 3, "created_at": datetime.now(timezone.utc)}
        with patch("cairn.core.agent_memory.get_or_create_project", return_value=10):
            store.store_learning("agent-1", "proj", "Something learned")

        call_args = db.execute_one.call_args
        # importance should be 0.6 (default)
        assert 0.6 in call_args[0][1]


class TestRecallLearnings:
    """Test learning retrieval."""

    def test_recall_basic(self):
        store, db = _make_store()
        db.execute.return_value = [
            {
                "id": 1, "agent_name": "agent-1", "content": "Use fixtures",
                "learning_type": "convention", "importance": 0.7,
                "work_item_display_id": "ca-42", "project": "proj",
                "created_at": datetime.now(timezone.utc),
            },
        ]
        with patch("cairn.core.agent_memory.get_project", return_value=10):
            results = store.recall_learnings("agent-1", "proj")

        assert len(results) == 1
        assert results[0]["content"] == "Use fixtures"
        assert results[0]["learning_type"] == "convention"

    def test_recall_no_project(self):
        """Recall across all projects."""
        store, db = _make_store()
        db.execute.return_value = []
        results = store.recall_learnings("agent-1")
        assert results == []
        # Should not have project_id WHERE condition
        sql = db.execute.call_args[0][0]
        assert "al.project_id = %s" not in sql

    def test_recall_with_type_filter(self):
        store, db = _make_store()
        db.execute.return_value = []
        with patch("cairn.core.agent_memory.get_project", return_value=10):
            store.recall_learnings("agent-1", "proj", learning_type="mistake")

        sql = db.execute.call_args[0][0]
        assert "learning_type" in sql

    def test_recall_empty_project(self):
        """Unknown project returns empty list."""
        store, db = _make_store()
        with patch("cairn.core.agent_memory.get_project", return_value=None):
            results = store.recall_learnings("agent-1", "nonexistent")

        assert results == []


class TestDeactivateLearning:
    """Test learning deactivation."""

    def test_deactivate(self):
        store, db = _make_store()
        result = store.deactivate_learning(42, reason="outdated")
        assert result["id"] == 42
        assert result["active"] is False
        db.execute.assert_called_once()
        db.commit.assert_called_once()


class TestBriefingContext:
    """Test briefing context generation."""

    def test_briefing_context_format(self):
        store, db = _make_store()
        db.execute.return_value = [
            {
                "id": 1, "agent_name": "agent-1", "content": "Use fixtures",
                "learning_type": "convention", "importance": 0.7,
                "work_item_display_id": "ca-42", "project": "proj",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": 2, "agent_name": "agent-1", "content": "Run tests first",
                "learning_type": "pattern", "importance": 0.6,
                "work_item_display_id": None, "project": "proj",
                "created_at": datetime.now(timezone.utc),
            },
        ]
        with patch("cairn.core.agent_memory.get_project", return_value=10):
            ctx = store.briefing_context("agent-1", "proj")

        assert len(ctx) == 2
        assert ctx[0]["type"] == "convention"
        assert ctx[0]["content"] == "Use fixtures"
        assert ctx[0]["source"] == "ca-42"
        assert ctx[1]["source"] == ""

    def test_briefing_context_empty(self):
        store, db = _make_store()
        db.execute.return_value = []
        with patch("cairn.core.agent_memory.get_project", return_value=10):
            ctx = store.briefing_context("agent-1", "proj")
        assert ctx == []


class TestExtractFromDeliverable:
    """Test learning extraction from deliverables."""

    def test_extract_decisions(self):
        store, db = _make_store()
        db.execute_one.side_effect = [
            {"id": i, "created_at": datetime.now(timezone.utc)}
            for i in range(1, 10)
        ]
        deliverable = {
            "decisions": ["Use JWT for auth", "Store tokens in Redis"],
        }
        with patch("cairn.core.agent_memory.get_or_create_project", return_value=10):
            stored = store.extract_from_deliverable(
                "agent-1", "proj", deliverable, work_item_id="ca-42",
            )

        assert len(stored) == 2
        assert all(s["stored"] for s in stored)

    def test_extract_learnings(self):
        store, db = _make_store()
        db.execute_one.side_effect = [
            {"id": i, "created_at": datetime.now(timezone.utc)}
            for i in range(1, 10)
        ]
        deliverable = {
            "learnings": ["fnmatch works for glob patterns", "Always test edge cases"],
        }
        with patch("cairn.core.agent_memory.get_or_create_project", return_value=10):
            stored = store.extract_from_deliverable("agent-1", "proj", deliverable)

        assert len(stored) == 2

    def test_extract_from_metadata(self):
        store, db = _make_store()
        db.execute_one.side_effect = [
            {"id": i, "created_at": datetime.now(timezone.utc)}
            for i in range(1, 10)
        ]
        deliverable = {
            "metadata": {
                "decisions": [{"content": "Use PostgreSQL"}],
                "learnings": ["DB migrations are order-dependent"],
            },
        }
        with patch("cairn.core.agent_memory.get_or_create_project", return_value=10):
            stored = store.extract_from_deliverable("agent-1", "proj", deliverable)

        assert len(stored) == 2

    def test_extract_empty_deliverable(self):
        store, db = _make_store()
        deliverable = {}
        with patch("cairn.core.agent_memory.get_or_create_project", return_value=10):
            stored = store.extract_from_deliverable("agent-1", "proj", deliverable)

        assert stored == []

    def test_extract_handles_dict_decisions(self):
        store, db = _make_store()
        db.execute_one.side_effect = [
            {"id": 1, "created_at": datetime.now(timezone.utc)},
        ]
        deliverable = {
            "decisions": [{"content": "Use JWT", "author": "agent-1"}],
        }
        with patch("cairn.core.agent_memory.get_or_create_project", return_value=10):
            stored = store.extract_from_deliverable("agent-1", "proj", deliverable)

        assert len(stored) == 1
        # Verify the stored content includes the decision text
        call_args = db.execute_one.call_args_list[0]
        assert "Decision: Use JWT" in call_args[0][1]
