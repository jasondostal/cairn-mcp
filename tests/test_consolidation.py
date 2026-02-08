"""Test memory consolidation: LLM recommends merges/promotions/inactivations.

Tests use mock LLM/DB — no real calls. ConsolidationEngine:
1. Finds highly similar memory pairs (>0.85 cosine)
2. Asks LLM for recommendations
3. Optionally applies changes (dry_run=False)
4. Returns error when LLM unavailable (can't degrade to no-op)
"""

import json
from unittest.mock import MagicMock

import numpy as np

from cairn.config import LLMCapabilities
from cairn.core.consolidation import ConsolidationEngine

from tests.helpers import ExplodingLLM, MockLLM


def _make_memory_rows(n: int = 4) -> list[dict]:
    """Build fake memory rows with embeddings that form similar pairs."""
    rng = np.random.RandomState(42)
    dim = 384

    rows = []
    for i in range(n):
        # Make pairs similar: 0&1 similar, 2&3 similar
        if i % 2 == 0:
            base = rng.randn(dim)
            base /= np.linalg.norm(base)
            current = base
        else:
            # Very small noise to guarantee cosine similarity > 0.85
            vec = base + rng.randn(dim) * 0.005
            vec /= np.linalg.norm(vec)
            current = vec

        embedding_str = "[" + ",".join(str(x) for x in current) + "]"
        rows.append({
            "id": i + 1,
            "content": f"Memory {i + 1} content.",
            "summary": f"Summary of memory {i + 1}.",
            "memory_type": "note",
            "importance": 0.5,
            "tags": ["test"],
            "auto_tags": [],
            "embedding": embedding_str,
            "created_at": f"2026-01-{15 + i}T10:00:00+00:00",
        })

    return rows


# ============================================================
# Dry Run
# ============================================================

def test_consolidation_dry_run():
    """Dry run returns recommendations without applying."""
    response = json.dumps([
        {"action": "merge", "inactivate_id": 2, "keep_id": 1, "reason": "Duplicate content"},
    ])
    db = MagicMock()
    db.execute.return_value = _make_memory_rows(4)
    embedding = MagicMock()

    engine = ConsolidationEngine(
        db, embedding,
        llm=MockLLM(response),
        capabilities=LLMCapabilities(consolidation=True),
    )

    result = engine.consolidate("test-project", dry_run=True)

    assert result["applied"] is False
    assert result["memory_count"] == 4
    assert len(result["recommendations"]) >= 1


# ============================================================
# No LLM
# ============================================================

def test_consolidation_no_llm():
    """Without LLM, returns error (consolidation requires LLM)."""
    db = MagicMock()
    embedding = MagicMock()

    engine = ConsolidationEngine(db, embedding, llm=None, capabilities=None)

    result = engine.consolidate("test-project")
    assert "error" in result
    assert "requires LLM" in result["error"]


# ============================================================
# Few Memories
# ============================================================

def test_consolidation_few_memories():
    """With fewer than 2 memories, returns empty results."""
    db = MagicMock()
    db.execute.return_value = [_make_memory_rows(1)[0]]
    embedding = MagicMock()

    engine = ConsolidationEngine(
        db, embedding,
        llm=MockLLM("[]"),
        capabilities=LLMCapabilities(consolidation=True),
    )

    result = engine.consolidate("test-project")

    assert result["memory_count"] == 1
    assert result["candidates"] == []
    assert result["recommendations"] == []


# ============================================================
# Apply (dry_run=False)
# ============================================================

def test_consolidation_apply():
    """With dry_run=False, recommendations are applied."""
    response = json.dumps([
        {"action": "inactivate", "memory_id": 2, "reason": "Outdated"},
    ])
    db = MagicMock()
    db.execute.return_value = _make_memory_rows(4)
    embedding = MagicMock()

    engine = ConsolidationEngine(
        db, embedding,
        llm=MockLLM(response),
        capabilities=LLMCapabilities(consolidation=True),
    )

    result = engine.consolidate("test-project", dry_run=False)

    assert result["applied"] is True
    assert result["applied_count"] >= 1
    db.commit.assert_called()
