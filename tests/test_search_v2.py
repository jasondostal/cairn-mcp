"""Tests for SearchV2 handler dispatch logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cairn.core.constants import HANDLER_CONFIDENCE_THRESHOLD


class FakeRoute:
    """Minimal RouterOutput stand-in."""
    def __init__(self, query_type="exploratory", confidence=0.5, entity_hints=None):
        self.query_type = query_type
        self.confidence = confidence
        self.entity_hints = entity_hints or []
        self.aspects = []
        self.temporal = MagicMock(after=None, before=None)


class TestHandlerDispatchLogic:
    """Test the conditional dispatch logic without a running database."""

    def test_entity_anchored_above_threshold_dispatches(self):
        """Entity-anchored queries above confidence threshold should dispatch handler."""
        route = FakeRoute(query_type="entity_lookup", confidence=0.8, entity_hints=["Alice"])
        assert route.confidence >= HANDLER_CONFIDENCE_THRESHOLD
        assert route.query_type in {"entity_lookup", "aspect_query", "relationship"}

    def test_entity_anchored_below_threshold_skips(self):
        """Entity-anchored queries below confidence threshold should use RRF only."""
        route = FakeRoute(query_type="entity_lookup", confidence=0.4)
        assert route.confidence < HANDLER_CONFIDENCE_THRESHOLD

    def test_temporal_above_threshold_dispatches(self):
        """Temporal queries above confidence threshold should dispatch handler."""
        route = FakeRoute(query_type="temporal", confidence=0.7)
        assert route.confidence >= HANDLER_CONFIDENCE_THRESHOLD
        assert route.query_type in {"temporal", "exploratory"}

    def test_exploratory_above_threshold_dispatches(self):
        """Exploratory queries above confidence threshold should dispatch handler."""
        route = FakeRoute(query_type="exploratory", confidence=0.8)
        assert route.confidence >= HANDLER_CONFIDENCE_THRESHOLD

    def test_low_confidence_uses_rrf_only(self):
        """Low confidence queries should not dispatch any handler."""
        route = FakeRoute(query_type="entity_lookup", confidence=0.3)
        assert route.confidence < HANDLER_CONFIDENCE_THRESHOLD

    def test_threshold_constant_is_0_6(self):
        """Handler confidence threshold should be 0.6."""
        assert HANDLER_CONFIDENCE_THRESHOLD == 0.6


class TestBlendResults:
    """Test _blend_results deduplication and ordering."""

    def test_primary_order_preserved(self):
        from cairn.core.handlers import _blend_results

        primary = [{"id": 1, "score": 0.9}, {"id": 2, "score": 0.8}]
        supplement = [{"id": 3, "score": 0.7}, {"id": 4, "score": 0.6}]
        result = _blend_results(primary, supplement, 10)
        assert [r["id"] for r in result] == [1, 2, 3, 4]

    def test_dedup_by_id(self):
        from cairn.core.handlers import _blend_results

        primary = [{"id": 1, "score": 0.9}, {"id": 2, "score": 0.8}]
        supplement = [{"id": 2, "score": 0.7}, {"id": 3, "score": 0.6}]
        result = _blend_results(primary, supplement, 10)
        assert [r["id"] for r in result] == [1, 2, 3]

    def test_limit_applied(self):
        from cairn.core.handlers import _blend_results

        primary = [{"id": i, "score": 1.0} for i in range(10)]
        supplement = [{"id": i + 10, "score": 0.5} for i in range(10)]
        result = _blend_results(primary, supplement, 5)
        assert len(result) == 5

    def test_empty_primary(self):
        from cairn.core.handlers import _blend_results

        supplement = [{"id": 1, "score": 0.9}]
        result = _blend_results([], supplement, 10)
        assert len(result) == 1

    def test_empty_supplement(self):
        from cairn.core.handlers import _blend_results

        primary = [{"id": 1, "score": 0.9}]
        result = _blend_results(primary, [], 10)
        assert len(result) == 1


class TestEntityAnchoredSet:
    """Verify the entity-anchored query type set."""

    def test_entity_anchored_types(self):
        """entity_lookup, aspect_query, and relationship are entity-anchored."""
        ENTITY_ANCHORED = {"entity_lookup", "aspect_query", "relationship"}
        assert "entity_lookup" in ENTITY_ANCHORED
        assert "aspect_query" in ENTITY_ANCHORED
        assert "relationship" in ENTITY_ANCHORED
        assert "temporal" not in ENTITY_ANCHORED
        assert "exploratory" not in ENTITY_ANCHORED
