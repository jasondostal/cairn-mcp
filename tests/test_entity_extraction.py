"""Tests for entity extraction in the enrichment pipeline."""

import json
from tests.helpers import MockLLM, ExplodingLLM
from cairn.core.enrichment import Enricher


def test_entities_extracted_from_enrichment():
    """Enricher should extract entities from LLM response."""
    response = json.dumps({
        "tags": ["docker", "deployment"],
        "importance": 0.7,
        "memory_type": "note",
        "summary": "Deployed to prod-1.",
        "entities": ["Docker", "prod-1", "Alice"],
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("Deployed Docker container to prod-1 with Alice.")

    assert "entities" in result
    assert result["entities"] == ["Docker", "prod-1", "Alice"]


def test_entities_preserve_case():
    """Entity names should preserve original casing."""
    response = json.dumps({
        "tags": ["test"],
        "importance": 0.5,
        "memory_type": "note",
        "summary": "Test.",
        "entities": ["Caroline Smith", "New York City", "OpenAI"],
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("content")

    assert result["entities"] == ["Caroline Smith", "New York City", "OpenAI"]


def test_entities_capped_at_15():
    """Entities should be capped at 15."""
    entities = [f"Entity{i}" for i in range(20)]
    response = json.dumps({
        "tags": ["test"],
        "importance": 0.5,
        "memory_type": "note",
        "summary": "Test.",
        "entities": entities,
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("content")

    assert len(result["entities"]) == 15


def test_entities_empty_when_none_found():
    """Entities should be empty list when LLM returns none."""
    response = json.dumps({
        "tags": ["test"],
        "importance": 0.5,
        "memory_type": "note",
        "summary": "Test.",
        "entities": [],
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("content")

    assert result["entities"] == []


def test_entities_missing_field_backward_compat():
    """Enrichment should work even when entities field is missing (backward compat)."""
    response = json.dumps({
        "tags": ["test"],
        "importance": 0.5,
        "memory_type": "note",
        "summary": "Test.",
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("content")

    # Should still succeed, entities defaults to empty
    assert result.get("entities", []) == []


def test_entities_strips_whitespace():
    """Entity names should have whitespace stripped."""
    response = json.dumps({
        "tags": ["test"],
        "importance": 0.5,
        "memory_type": "note",
        "summary": "Test.",
        "entities": ["  Docker  ", "prod-1", "  "],
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("content")

    # Empty strings after stripping should be filtered out
    assert result["entities"] == ["Docker", "prod-1"]


def test_entities_handles_non_string_items():
    """Non-string items in entities list should be converted to strings."""
    response = json.dumps({
        "tags": ["test"],
        "importance": 0.5,
        "memory_type": "note",
        "summary": "Test.",
        "entities": ["Docker", 42, True],
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("content")

    assert "Docker" in result["entities"]
    assert "42" in result["entities"]


def test_entities_llm_failure_returns_empty():
    """LLM failure should return empty dict (no entities)."""
    enricher = Enricher(ExplodingLLM())
    result = enricher.enrich("content")

    assert result == {}
