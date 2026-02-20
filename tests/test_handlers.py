"""Tests for search handler dispatch and fallback logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cairn.core.handlers import (
    HANDLERS,
    SearchContext,
    _blend_results,
    _fetch_memories_by_ids,
    handle_aspect_query,
    handle_entity_lookup,
    handle_exploratory,
    handle_relationship,
    handle_temporal,
)


class TestHandlerRegistry:
    """Test the handler dispatch map."""

    def test_five_handlers_registered(self):
        assert len(HANDLERS) == 5

    def test_all_query_types_covered(self):
        expected = {"aspect_query", "entity_lookup", "temporal", "exploratory", "relationship"}
        assert set(HANDLERS.keys()) == expected

    def test_handlers_are_callable(self):
        for name, handler in HANDLERS.items():
            assert callable(handler), f"{name} handler is not callable"


class TestHandlerFallbackBehavior:
    """Test that handlers gracefully handle missing graph."""

    def _make_ctx(self, graph=None, entity_hints=None, aspects=None, query_type="exploratory"):
        route = MagicMock()
        route.query_type = query_type
        route.entity_hints = entity_hints or []
        route.aspects = aspects or []
        route.temporal = MagicMock(after=None, before=None)
        route.confidence = 0.8

        return SearchContext(
            query="test query",
            route=route,
            project_id=1,
            project_name="test",
            db=MagicMock(),
            embedding=MagicMock(),
            graph=graph,
            limit=10,
        )

    @patch("cairn.core.handlers._vector_search", return_value=[{"id": 1, "score": 0.9}])
    def test_aspect_query_no_graph_falls_back(self, mock_vs):
        ctx = self._make_ctx(graph=None, aspects=["Identity"])
        result = handle_aspect_query(ctx)
        assert result == [{"id": 1, "score": 0.9}]

    @patch("cairn.core.handlers._vector_search", return_value=[{"id": 2, "score": 0.8}])
    def test_entity_lookup_no_graph_falls_back(self, mock_vs):
        ctx = self._make_ctx(graph=None, entity_hints=["Alice"])
        result = handle_entity_lookup(ctx)
        assert result == [{"id": 2, "score": 0.8}]

    def test_relationship_no_graph_returns_empty(self):
        ctx = self._make_ctx(graph=None, entity_hints=["Alice", "Bob"])
        result = handle_relationship(ctx)
        assert result == []

    def test_relationship_one_entity_returns_empty(self):
        ctx = self._make_ctx(graph=MagicMock(), entity_hints=["Alice"])
        result = handle_relationship(ctx)
        assert result == []


class TestBlendLogic:
    """Test _blend_results merging behavior — score-ordered, both sources compete."""

    def test_blend_sorts_by_score(self):
        handler = [{"id": 10, "score": 1.0}, {"id": 20, "score": 0.9}]
        rrf = [{"id": 30, "score": 0.8}, {"id": 10, "score": 0.7}]
        result = _blend_results(handler, rrf, 10)
        # Sorted by score: id=10 (1.0), id=20 (0.9), id=30 (0.8). Dedup keeps first.
        ids = [r["id"] for r in result]
        assert ids == [10, 20, 30]

    def test_blend_dedup_keeps_first_occurrence(self):
        rrf = [{"id": 30, "score": 0.8}, {"id": 10, "score": 0.7}]
        handler = [{"id": 10, "score": 1.0}, {"id": 20, "score": 0.9}]
        result = _blend_results(rrf, handler, 10)
        # id=10 deduped (rrf's 0.7 kept, not handler's 1.0), then sorted by score
        # id=20 (0.9) > id=30 (0.8) > id=10 (0.7)
        ids = [r["id"] for r in result]
        assert ids == [20, 30, 10]

    def test_empty_handler_returns_rrf(self):
        rrf = [{"id": 1, "score": 0.9}]
        result = _blend_results([], rrf, 10)
        assert len(result) == 1
        assert result[0]["id"] == 1
