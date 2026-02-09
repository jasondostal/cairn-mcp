"""Test contradiction escalation on store and contradiction-aware search ranking.

TestContradictionEscalation: verifies that _escalate_contradictions() surfaces
high-importance contradicted memories in the store response.

TestContradictionAwareSearch: verifies that _apply_contradiction_penalty() demotes
contradicted memories in search results.
"""

import json
from unittest.mock import MagicMock, call

from cairn.config import LLMCapabilities
from cairn.core.memory import MemoryStore
from cairn.core.search import SearchEngine

from tests.helpers import MockLLM


# ============================================================
# Helpers
# ============================================================

def _make_memory_store(llm=None, capabilities=None):
    """Build a MemoryStore with mock DB/embedding."""
    db = MagicMock()
    embedding = MagicMock()
    embedding.embed.return_value = [0.1] * 384
    return MemoryStore(db, embedding, llm=llm, capabilities=capabilities), db


def _make_search_engine():
    """Build a SearchEngine with mock DB/embedding."""
    db = MagicMock()
    embedding = MagicMock()
    embedding.embed.return_value = [0.1] * 384
    return SearchEngine(db, embedding), db


# ============================================================
# TestContradictionEscalation
# ============================================================

class TestContradictionEscalation:

    def test_escalates_high_importance_contradiction(self):
        """Store detects contradicts relation against importance 0.9 memory -> conflicts populated."""
        auto_relations = [
            {"id": 42, "relation": "contradicts"},
            {"id": 17, "relation": "extends"},
        ]

        store, db = _make_memory_store()

        # Mock the fetch of target memories
        db.execute.return_value = [
            {"id": 42, "summary": "Deploy from git repo...", "importance": 0.9, "memory_type": "decision"},
        ]

        result = store._escalate_contradictions(auto_relations)

        assert len(result) == 1
        assert result[0]["id"] == 42
        assert result[0]["summary"] == "Deploy from git repo..."
        assert result[0]["importance"] == 0.9
        assert "inactivating" in result[0]["action"].lower()

    def test_no_escalation_for_low_importance(self):
        """Contradicts relation against importance 0.3 memory -> conflicts empty."""
        auto_relations = [
            {"id": 42, "relation": "contradicts"},
        ]

        store, db = _make_memory_store()

        db.execute.return_value = [
            {"id": 42, "summary": "Old low-importance note.", "importance": 0.3, "memory_type": "note"},
        ]

        result = store._escalate_contradictions(auto_relations)

        assert result == []

    def test_no_escalation_when_no_contradictions(self):
        """Only extends/related relations -> conflicts empty, no DB query."""
        auto_relations = [
            {"id": 42, "relation": "extends"},
            {"id": 17, "relation": "related"},
        ]

        store, db = _make_memory_store()

        result = store._escalate_contradictions(auto_relations)

        assert result == []
        # Should not query DB since there are no contradictions
        db.execute.assert_not_called()

    def test_escalation_with_extraction_disabled(self):
        """When relationship_extract=False, auto_relations is empty -> conflicts empty."""
        # Simulate what happens when extraction is off: auto_relations = []
        store, db = _make_memory_store()

        result = store._escalate_contradictions([])

        assert result == []
        db.execute.assert_not_called()


# ============================================================
# TestContradictionAwareSearch
# ============================================================

class TestContradictionAwareSearch:

    def test_contradicted_memory_ranks_lower(self):
        """Memory with incoming contradiction gets score * 0.5, ranks below non-contradicted."""
        engine, db = _make_search_engine()

        scored = {10: 0.8, 20: 0.6}

        # Memory 10 has an incoming contradiction
        db.execute.return_value = [{"target_id": 10}]

        result = engine._apply_contradiction_penalty(scored)

        assert result[10] == 0.8 * 0.5  # penalized
        assert result[20] == 0.6         # unchanged
        # Memory 20 should now rank higher than memory 10
        assert result[20] > result[10]

    def test_non_contradicted_memory_unaffected(self):
        """Memory with no contradictions keeps original score."""
        engine, db = _make_search_engine()

        scored = {10: 0.8, 20: 0.6}

        # No contradictions found
        db.execute.return_value = []

        result = engine._apply_contradiction_penalty(scored)

        assert result[10] == 0.8
        assert result[20] == 0.6

    def test_no_penalty_when_no_relations(self):
        """Empty scored dict -> returned unchanged."""
        engine, db = _make_search_engine()

        result = engine._apply_contradiction_penalty({})

        assert result == {}
        # Should not query DB when there are no IDs
        db.execute.assert_not_called()
