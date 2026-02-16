"""Tests for QueryRouter classification."""

from __future__ import annotations

import pytest

from cairn.core.router import RouterOutput, VALID_QUERY_TYPES, VALID_ASPECTS


class TestRouterOutput:
    """Test RouterOutput model validation."""

    def test_default_values(self):
        route = RouterOutput()
        assert route.query_type == "exploratory"
        assert route.confidence == 0.5
        assert route.entity_hints == []
        assert route.aspects == []

    def test_valid_query_types(self):
        for qt in VALID_QUERY_TYPES:
            route = RouterOutput(query_type=qt)
            assert route.query_type == qt

    def test_invalid_query_type_defaults_to_exploratory(self):
        route = RouterOutput(query_type="invalid_type")
        assert route.query_type == "exploratory"

    def test_confidence_clamped_high(self):
        route = RouterOutput(confidence=1.5)
        assert route.confidence == 1.0

    def test_confidence_clamped_low(self):
        route = RouterOutput(confidence=-0.5)
        assert route.confidence == 0.0

    def test_aspects_filtered(self):
        route = RouterOutput(aspects=["Identity", "fake_aspect", "Knowledge"])
        assert "Identity" in route.aspects
        assert "Knowledge" in route.aspects
        assert "fake_aspect" not in route.aspects

    def test_entity_hints_preserved(self):
        route = RouterOutput(entity_hints=["Alice", "Bob"])
        assert route.entity_hints == ["Alice", "Bob"]


class TestValidSets:
    """Test the valid query types and aspects."""

    def test_five_query_types(self):
        assert len(VALID_QUERY_TYPES) == 5
        expected = {"aspect_query", "entity_lookup", "temporal", "exploratory", "relationship"}
        assert VALID_QUERY_TYPES == expected

    def test_eleven_aspects(self):
        assert len(VALID_ASPECTS) == 11
