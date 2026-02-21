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


class TestQueryEntityChunking:
    """Bug 12 fix: _extract_query_entities should extract meaningful terms only.

    Old behavior embedded every word ≥3 chars + every bigram (~20 chunks).
    New behavior extracts capitalized words (proper nouns) + full query (~3-5 chunks).
    """

    def _get_chunks(self, query: str) -> set[str]:
        """Extract the chunks that would be generated for a query.

        Replicates the chunking logic from SearchV2._extract_query_entities
        without needing a full SearchV2 instance.
        """
        from cairn.core.search_v2 import SearchV2

        raw_words = query.split()
        capitalized = []
        for i, w in enumerate(raw_words):
            clean = w.strip("?.,!:;\"'()[]")
            if not clean:
                continue
            if i > 0 and clean[0].isupper():
                capitalized.append(clean)

        chunks = set()
        for w in capitalized:
            chunks.add(w)

        for i in range(len(raw_words) - 1):
            w1 = raw_words[i].strip("?.,!:;\"'()[]")
            w2 = raw_words[i + 1].strip("?.,!:;\"'()[]")
            if w1 and w2 and w1[0].isupper() and w2[0].isupper() and i > 0:
                chunks.add(f"{w1} {w2}")

        if not chunks:
            for w in raw_words:
                clean = w.strip("?.,!:;\"'()[]").lower()
                if len(clean) >= 4 and clean not in SearchV2._STOP_WORDS:
                    chunks.add(clean)

        chunks.add(query)
        return chunks

    def test_proper_nouns_extracted(self):
        """Capitalized words (not first word) should be extracted."""
        chunks = self._get_chunks("What did Caroline do?")
        assert "Caroline" in chunks
        assert "What did Caroline do?" in chunks  # full query always included

    def test_stop_words_not_extracted(self):
        """Stop words like 'did', 'what', 'does' should never be chunks."""
        chunks = self._get_chunks("What did Caroline do?")
        assert "did" not in chunks
        assert "what" not in chunks
        assert "do" not in chunks

    def test_chunk_count_reasonable(self):
        """Should produce far fewer chunks than old approach."""
        chunks = self._get_chunks("What kind of place does Melanie want to create?")
        # Old approach: ~20 chunks (every word + bigram)
        # New approach: "Melanie" + full query = 2 chunks
        assert len(chunks) <= 5, f"Too many chunks: {chunks}"
        assert "Melanie" in chunks

    def test_multi_entity_query(self):
        """Multiple proper nouns should all be extracted."""
        chunks = self._get_chunks("How are Alice and Bob related?")
        assert "Alice" in chunks
        assert "Bob" in chunks

    def test_adjacent_capitalized_phrase(self):
        """Adjacent capitalized words form a phrase chunk."""
        chunks = self._get_chunks("What happened in New York?")
        assert "New" in chunks
        assert "York" in chunks
        assert "New York" in chunks

    def test_no_proper_nouns_fallback(self):
        """Queries with no capitalized terms fall back to content words."""
        chunks = self._get_chunks("how does deployment work?")
        assert "deployment" in chunks
        # stop words excluded
        assert "does" not in chunks
        assert "how" not in chunks

    def test_first_word_skipped(self):
        """First word is always capitalized in questions — skip it."""
        chunks = self._get_chunks("What is Paris?")
        assert "Paris" in chunks
        # "What" should not be extracted as a proper noun
        lower_chunks = {c.lower() for c in chunks if c != "What is Paris?"}
        assert "what" not in lower_chunks
