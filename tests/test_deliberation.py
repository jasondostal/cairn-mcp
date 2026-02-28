"""Tests for thinking tool evolution — deliberation protocol (ca-102)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from cairn.core.constants import VALID_THOUGHT_TYPES


class TestNewThoughtTypes:
    """Verify new deliberation thought types are registered."""

    def test_tradeoff_type_valid(self):
        assert "tradeoff" in VALID_THOUGHT_TYPES

    def test_decision_type_valid(self):
        assert "decision" in VALID_THOUGHT_TYPES

    def test_risk_type_valid(self):
        assert "risk" in VALID_THOUGHT_TYPES

    def test_dependency_type_valid(self):
        assert "dependency" in VALID_THOUGHT_TYPES

    def test_scope_type_valid(self):
        assert "scope" in VALID_THOUGHT_TYPES

    def test_original_types_preserved(self):
        """Ensure original thought types still exist."""
        originals = [
            "observation", "hypothesis", "question", "reasoning", "conclusion",
            "assumption", "analysis", "general", "alternative", "branch",
            "insight", "realization", "pattern", "challenge", "response",
        ]
        for t in originals:
            assert t in VALID_THOUGHT_TYPES, f"{t} missing from VALID_THOUGHT_TYPES"


class TestSummarizeDeliberation:
    """Test ThinkingEngine.summarize_deliberation()."""

    def _make_engine(self):
        from cairn.core.thinking import ThinkingEngine
        db = MagicMock()
        engine = ThinkingEngine(db)
        return engine, db

    def _mock_sequence(self, db, thoughts):
        """Set up DB mocks for get_sequence to return given thoughts."""
        seq_row = {
            "id": 1, "goal": "Decide auth approach", "status": "completed",
            "created_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
            "reopened_at": None,
            "project": "cairn",
        }
        thought_rows = [
            {
                "id": i + 1,
                "thought_type": t.get("type", "general"),
                "content": t["content"],
                "branch_name": t.get("branch"),
                "author": t.get("author"),
                "created_at": datetime.now(timezone.utc),
            }
            for i, t in enumerate(thoughts)
        ]
        db.execute_one.return_value = seq_row
        db.execute.return_value = thought_rows

    def test_basic_summary(self):
        engine, db = self._make_engine()
        self._mock_sequence(db, [
            {"type": "observation", "content": "Current auth uses sessions"},
            {"type": "tradeoff", "content": "JWT is stateless but harder to revoke"},
            {"type": "decision", "content": "Use JWT with short expiry + refresh tokens"},
            {"type": "conclusion", "content": "JWT with 15min access + 7d refresh"},
        ])

        result = engine.summarize_deliberation(1)

        assert result["sequence_id"] == 1
        assert result["goal"] == "Decide auth approach"
        assert result["total_thoughts"] == 4
        assert result["conclusion"] == "JWT with 15min access + 7d refresh"
        assert len(result["decisions"]) == 1
        assert len(result["tradeoffs"]) == 1
        assert result["decisions"][0]["content"] == "Use JWT with short expiry + refresh tokens"

    def test_risks_and_dependencies(self):
        engine, db = self._make_engine()
        self._mock_sequence(db, [
            {"type": "risk", "content": "Token theft via XSS", "author": "assistant"},
            {"type": "risk", "content": "Refresh token rotation complexity", "author": "user"},
            {"type": "dependency", "content": "Needs Redis for token blacklist"},
            {"type": "conclusion", "content": "Accept risks with mitigation plan"},
        ])

        result = engine.summarize_deliberation(1)

        assert len(result["risks"]) == 2
        assert result["risks"][0]["author"] == "assistant"
        assert result["risks"][1]["author"] == "user"
        assert len(result["dependencies"]) == 1

    def test_open_questions(self):
        engine, db = self._make_engine()
        self._mock_sequence(db, [
            {"type": "question", "content": "What about OAuth providers?"},
            {"type": "question", "content": "Do we need 2FA?"},
            {"type": "reasoning", "content": "OAuth adds complexity but improves UX"},
        ])

        result = engine.summarize_deliberation(1)

        assert len(result["open_questions"]) == 2
        assert result["conclusion"] is None  # No conclusion yet

    def test_insights_merged(self):
        """Both 'insight' and 'realization' types appear in insights list."""
        engine, db = self._make_engine()
        self._mock_sequence(db, [
            {"type": "insight", "content": "Auth is the foundation for everything else"},
            {"type": "realization", "content": "We need to support API keys too"},
        ])

        result = engine.summarize_deliberation(1)
        assert len(result["insights"]) == 2

    def test_branch_analysis(self):
        engine, db = self._make_engine()
        self._mock_sequence(db, [
            {"type": "alternative", "content": "Option A: JWT", "branch": "jwt"},
            {"type": "reasoning", "content": "Stateless and scalable", "branch": "jwt"},
            {"type": "alternative", "content": "Option B: Sessions", "branch": "sessions"},
            {"type": "reasoning", "content": "Simpler revocation", "branch": "sessions"},
            {"type": "reasoning", "content": "More server state needed", "branch": "sessions"},
        ])

        result = engine.summarize_deliberation(1)
        assert result["branches"] == {"jwt": 2, "sessions": 3}

    def test_thought_type_counts(self):
        engine, db = self._make_engine()
        self._mock_sequence(db, [
            {"type": "observation", "content": "Obs 1"},
            {"type": "observation", "content": "Obs 2"},
            {"type": "tradeoff", "content": "TO 1"},
            {"type": "decision", "content": "Dec 1"},
        ])

        result = engine.summarize_deliberation(1)
        assert result["thought_type_counts"]["observation"] == 2
        assert result["thought_type_counts"]["tradeoff"] == 1
        assert result["thought_type_counts"]["decision"] == 1

    def test_empty_sequence(self):
        engine, db = self._make_engine()
        self._mock_sequence(db, [])

        result = engine.summarize_deliberation(1)
        assert result["total_thoughts"] == 0
        assert result["conclusion"] is None
        assert result["decisions"] == []
        assert result["risks"] == []

    def test_last_conclusion_wins(self):
        """When multiple conclusions exist, the last one is used."""
        engine, db = self._make_engine()
        self._mock_sequence(db, [
            {"type": "conclusion", "content": "First attempt: use sessions"},
            {"type": "reasoning", "content": "Actually, JWT is better"},
            {"type": "conclusion", "content": "Final: use JWT"},
        ])

        result = engine.summarize_deliberation(1)
        assert result["conclusion"] == "Final: use JWT"
