"""Test relationship extraction: LLM identifies relations between memories on store.

Tests use mock LLM/DB — no real calls. MemoryStore._extract_relationships():
1. Vector-searches for nearest neighbors
2. Asks LLM which are genuinely related
3. Creates memory_relations entries with typed relations
4. Falls back to empty list on failure
"""

import json
from unittest.mock import MagicMock, call

from cairn.config import LLMCapabilities
from cairn.core.memory import MemoryStore

from tests.helpers import ExplodingLLM, MockLLM


def _make_store(llm, capabilities=None):
    """Build a MemoryStore with mock DB/embedding."""
    db = MagicMock()
    embedding = MagicMock()
    return MemoryStore(db, embedding, llm=llm, capabilities=capabilities), db


# ============================================================
# Found Relationships
# ============================================================

def test_extract_relationships_found():
    """LLM finds genuine relationships among neighbors."""
    response = json.dumps([
        {"id": 42, "relation": "extends"},
        {"id": 17, "relation": "related"},
    ])
    capabilities = LLMCapabilities(relationship_extract=True)
    store, db = _make_store(MockLLM(response), capabilities)

    # Mock neighbor query results
    db.execute.return_value = [
        {"id": 42, "content": "Previous memory about Docker config.", "summary": "Docker config."},
        {"id": 17, "content": "Another memory about containers.", "summary": "Containers."},
        {"id": 99, "content": "Unrelated memory.", "summary": "Unrelated."},
    ]

    result = store._extract_relationships(
        memory_id=100,
        content="New Docker networking setup with bridge mode.",
        embedding=[0.1] * 384,
        project_id=1,
    )

    assert len(result) == 2
    assert result[0] == {"id": 42, "relation": "extends"}
    assert result[1] == {"id": 17, "relation": "related"}


# ============================================================
# No Candidates
# ============================================================

def test_extract_relationships_no_candidates():
    """No neighbors found returns empty list."""
    capabilities = LLMCapabilities(relationship_extract=True)
    store, db = _make_store(MockLLM("[]"), capabilities)

    db.execute.return_value = []

    result = store._extract_relationships(
        memory_id=100,
        content="Totally unique content.",
        embedding=[0.1] * 384,
        project_id=1,
    )

    assert result == []


# ============================================================
# LLM Failure
# ============================================================

def test_extract_relationships_llm_failure():
    """LLM failure returns empty list."""
    capabilities = LLMCapabilities(relationship_extract=True)
    store, db = _make_store(ExplodingLLM(), capabilities)

    db.execute.return_value = [
        {"id": 42, "content": "Some memory.", "summary": "Some summary."},
    ]

    result = store._extract_relationships(
        memory_id=100,
        content="New content.",
        embedding=[0.1] * 384,
        project_id=1,
    )

    assert result == []


# ============================================================
# Flag Off
# ============================================================

def test_extract_relationships_flag_off():
    """When flag is off, returns empty list without calling LLM."""
    capabilities = LLMCapabilities(relationship_extract=False)
    store, db = _make_store(MockLLM("should not be called"), capabilities)

    result = store._extract_relationships(
        memory_id=100,
        content="New content.",
        embedding=[0.1] * 384,
        project_id=1,
    )

    assert result == []
    # LLM should not have been called — verify no DB query for neighbors
    db.execute.assert_not_called()
