"""Test session synthesis: LLM creates narrative from session memories.

Tests use mock LLM/DB — no real calls. The SessionSynthesizer:
1. Fetches memories for a session
2. Calls LLM for narrative synthesis
3. Falls back to structured memory list on failure
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from cairn.config import LLMCapabilities
from cairn.core.synthesis import SessionSynthesizer

from tests.helpers import ExplodingLLM, MockLLM


def _make_memory_rows(n: int = 3) -> list[dict]:
    """Build fake memory rows."""
    return [
        {
            "id": i + 1,
            "content": f"Memory {i + 1} content about the session work.",
            "summary": f"Summary of memory {i + 1}.",
            "memory_type": "note",
            "importance": 0.5,
            "tags": ["test"],
            "auto_tags": [],
            "created_at": datetime(2026, 1, 15, 10 + i, 0, tzinfo=timezone.utc),
        }
        for i in range(n)
    ]


# ============================================================
# With LLM
# ============================================================

def test_synthesis_with_llm():
    """LLM produces a narrative from session memories."""
    narrative = "The session focused on implementing test coverage. Key decisions were made about mock patterns."
    db = MagicMock()
    db.execute.return_value = _make_memory_rows(3)

    synth = SessionSynthesizer(
        db,
        llm=MockLLM(narrative),
        capabilities=LLMCapabilities(session_synthesis=True),
    )

    result = synth.synthesize("test-project", "sprint-1")

    assert result["narrative"] == narrative
    assert result["memory_count"] == 3
    assert result["session_name"] == "sprint-1"
    assert result["project"] == "test-project"
    assert len(result["memories"]) == 3


# ============================================================
# Without LLM
# ============================================================

def test_synthesis_without_llm():
    """Without LLM, returns structured fallback (no narrative)."""
    db = MagicMock()
    db.execute.return_value = _make_memory_rows(3)

    synth = SessionSynthesizer(db, llm=None, capabilities=None)

    result = synth.synthesize("test-project", "sprint-1")

    assert result["narrative"] is None
    assert result["memory_count"] == 3
    assert len(result["memories"]) == 3


# ============================================================
# Empty Session
# ============================================================

def test_synthesis_empty_session():
    """Empty session returns gracefully."""
    db = MagicMock()
    db.execute.return_value = []

    synth = SessionSynthesizer(
        db,
        llm=MockLLM("some narrative"),
        capabilities=LLMCapabilities(session_synthesis=True),
    )

    result = synth.synthesize("test-project", "sprint-1")

    assert result["memory_count"] == 0
    assert result["narrative"] is None
    assert result["memories"] == []


# ============================================================
# LLM Failure
# ============================================================

def test_synthesis_llm_failure():
    """LLM failure returns fallback with structured data."""
    db = MagicMock()
    db.execute.return_value = _make_memory_rows(3)

    synth = SessionSynthesizer(
        db,
        llm=ExplodingLLM(),
        capabilities=LLMCapabilities(session_synthesis=True),
    )

    result = synth.synthesize("test-project", "sprint-1")

    assert result["narrative"] is None
    assert result["memory_count"] == 3
    assert len(result["memories"]) == 3
