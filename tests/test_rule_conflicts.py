"""Test rule conflict detection: LLM checks new rules against existing rules.

Tests use mock LLM/DB — no real calls. MemoryStore._check_rule_conflicts():
1. Fetches existing rules for project + __global__
2. Asks LLM for contradictions
3. Returns conflict list (advisory — rule is always stored)
4. Falls back to None on failure
"""

import json
from unittest.mock import MagicMock, patch

from cairn.config import LLMCapabilities
from cairn.core.memory import MemoryStore

from tests.helpers import ExplodingLLM, MockLLM


def _make_store(llm, capabilities=None):
    """Build a MemoryStore with mock DB/embedding."""
    db = MagicMock()
    embedding = MagicMock()
    store = MemoryStore(db, embedding, llm=llm, capabilities=capabilities)
    return store, db


# ============================================================
# Conflict Found
# ============================================================

def test_rule_conflict_found():
    """LLM detects a conflict between new and existing rule."""
    response = json.dumps([
        {"rule_id": 5, "conflict": "Contradicts timeout policy", "severity": "high"},
    ])
    capabilities = LLMCapabilities(rule_conflict_check=True)
    store, db = _make_store(MockLLM(response), capabilities)

    # Mock get_rules to return existing rules
    store.get_rules = MagicMock(return_value={
        "total": 1,
        "items": [
            {"id": 5, "content": "All API calls must timeout after 30 seconds.", "importance": 0.9, "project": "test", "tags": [], "created_at": "2026-01-01T00:00:00"},
        ],
    })

    result = store._check_rule_conflicts(
        "All API calls should have no timeout limit.",
        "test-project",
    )

    assert len(result) == 1
    assert result[0]["rule_id"] == 5
    assert result[0]["severity"] == "high"
    assert "timeout" in result[0]["conflict"].lower()


# ============================================================
# No Conflicts
# ============================================================

def test_rule_no_conflicts():
    """LLM finds no conflicts."""
    capabilities = LLMCapabilities(rule_conflict_check=True)
    store, db = _make_store(MockLLM("[]"), capabilities)

    store.get_rules = MagicMock(return_value={
        "total": 1,
        "items": [
            {"id": 5, "content": "Use Python 3.11+.", "importance": 0.7, "project": "test", "tags": [], "created_at": "2026-01-01T00:00:00"},
        ],
    })

    result = store._check_rule_conflicts("Use type hints everywhere.", "test-project")

    assert result == []


# ============================================================
# Non-Rule Skipped
# ============================================================

def test_rule_conflict_skipped_for_non_rules():
    """_check_rule_conflicts is only called for type='rule' in store().

    This test verifies the method returns None when the capability flag is off,
    which is the equivalent of the store() code not calling it for non-rules.
    """
    capabilities = LLMCapabilities(rule_conflict_check=False)
    store, db = _make_store(MockLLM("should not be called"), capabilities)

    result = store._check_rule_conflicts("Some note content", "test-project")
    assert result is None


# ============================================================
# LLM Failure
# ============================================================

def test_rule_conflict_llm_failure():
    """LLM failure returns None (rule still stored)."""
    capabilities = LLMCapabilities(rule_conflict_check=True)
    store, db = _make_store(ExplodingLLM(), capabilities)

    store.get_rules = MagicMock(return_value={
        "total": 1,
        "items": [
            {"id": 5, "content": "Some rule.", "importance": 0.7, "project": "test", "tags": [], "created_at": "2026-01-01T00:00:00"},
        ],
    })

    result = store._check_rule_conflicts("New rule.", "test-project")
    assert result is None


# ============================================================
# Flag Off
# ============================================================

def test_rule_conflict_flag_off():
    """When flag is off, returns None without calling LLM."""
    capabilities = LLMCapabilities(rule_conflict_check=False)
    store, db = _make_store(MockLLM("should not be called"), capabilities)

    result = store._check_rule_conflicts("New rule.", "test-project")
    assert result is None
