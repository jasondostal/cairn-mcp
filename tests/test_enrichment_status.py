"""Test enrichment status tracking — _status key in enrichment dict."""

import json

from cairn.core.enrichment import Enricher
from tests.helpers import ExplodingLLM, MockLLM


def test_complete_enrichment_has_complete_status():
    """Enrichment with entities returns _status=complete."""
    response = json.dumps({
        "tags": ["python"],
        "importance": 0.7,
        "memory_type": "learning",
        "summary": "A learning about Python.",
        "entities": ["Python", "testing"],
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("some content about Python testing")
    assert result["_status"] == "complete"
    assert len(result["entities"]) == 2


def test_partial_enrichment_has_partial_status():
    """Enrichment without entities returns _status=partial."""
    response = json.dumps({
        "tags": ["misc"],
        "importance": 0.5,
        "memory_type": "note",
        "summary": "A note.",
        "entities": [],
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("some vague content")
    assert result["_status"] == "partial"


def test_failed_enrichment_has_failed_status():
    """Failed enrichment returns _status=failed."""
    enricher = Enricher(ExplodingLLM())
    result = enricher.enrich("some content")
    assert result["_status"] == "failed"
    assert "tags" not in result
    assert "entities" not in result


def test_status_key_does_not_leak_into_tags():
    """_status should not appear in tags or entities."""
    response = json.dumps({
        "tags": ["python"],
        "importance": 0.7,
        "memory_type": "note",
        "summary": "A note.",
        "entities": ["Python"],
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("content")
    assert "_status" not in result.get("tags", [])
    assert "_status" not in result.get("entities", [])
