"""MCA (Multi-Candidate Assessment) — keyword coverage pre-filter.

Computes keyword overlap between query and memory content to eliminate
false positives before expensive reranking. Memories with zero
entity/keyword coverage are filtered out — they matched on semantic
similarity alone but lack the actual entities the query asks about.

Design: hard filter (not an RRF signal). Coverage threshold of 0.1
means ~1 query keyword must appear in the memory content. This catches
the "right pattern, wrong entity" problem that plagues vector search.
"""

from __future__ import annotations

import logging
import re
import time

logger = logging.getLogger(__name__)

# Stopwords — removed from both query and memory before coverage calculation.
# Tuned for conversational memory queries.
MCA_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "what", "when", "where", "who",
    "which", "how", "to", "of", "in", "on", "at", "by", "for",
    "with", "from", "about", "as", "into", "through", "during",
    "that", "this", "these", "those", "and", "or", "but", "if",
    "not", "no", "can", "may", "so", "just", "than", "then",
    "its", "my", "your", "his", "her", "our", "their",
    "i", "me", "we", "you", "he", "she", "it", "they", "them",
    "any", "all", "each", "every", "some", "many", "much",
    "also", "very", "too", "more", "most", "other", "another",
})

# Default coverage threshold — fraction of query keywords that must appear.
# 0.1 means ~1 keyword for most queries.
MCA_THRESHOLD = 0.1

# Widen the RRF candidate pool by this factor when MCA is enabled,
# since MCA will filter out a significant portion.
MCA_POOL_MULTIPLIER = 3

# Minimum keyword length to consider
MCA_MIN_WORD_LENGTH = 3

_WORD_RE = re.compile(r"\b\w+\b")


def extract_keywords(text: str) -> set[str]:
    """Extract content keywords from text, removing stopwords.

    Returns lowercase keyword set. Words shorter than MCA_MIN_WORD_LENGTH
    are excluded (along with stopwords).
    """
    words = _WORD_RE.findall(text.lower())
    return {
        w for w in words
        if len(w) >= MCA_MIN_WORD_LENGTH and w not in MCA_STOPWORDS
    }


def compute_coverage(query_keywords: set[str], memory_keywords: set[str]) -> float:
    """Compute keyword coverage: fraction of query keywords found in memory.

    Returns 0.0-1.0. Returns 0.0 if query has no keywords.
    """
    if not query_keywords:
        return 0.0
    overlap = len(query_keywords & memory_keywords)
    return overlap / len(query_keywords)


class MCAGate:
    """Multi-Candidate Assessment gate for search result filtering.

    Computes keyword coverage between query and each candidate memory,
    filtering out candidates below the coverage threshold. This eliminates
    semantically-similar-but-wrong-entity results that fool vector search.
    """

    def __init__(self, threshold: float = MCA_THRESHOLD):
        self.threshold = threshold

    def filter(
        self,
        query: str,
        candidates: list[dict],
        *,
        threshold: float | None = None,
    ) -> tuple[list[dict], dict]:
        """Filter candidates by keyword coverage.

        Args:
            query: The search query.
            candidates: List of dicts, each must have 'content' key.
            threshold: Override default coverage threshold.

        Returns:
            Tuple of (filtered_candidates, stats_dict).
            stats_dict contains: candidates_in, candidates_out, threshold,
            mean_coverage, elapsed_ms.
        """
        t0 = time.monotonic()
        effective_threshold = threshold if threshold is not None else self.threshold

        query_keywords = extract_keywords(query)

        if not query_keywords:
            # No meaningful keywords in query — skip filtering
            stats = {
                "candidates_in": len(candidates),
                "candidates_out": len(candidates),
                "threshold": effective_threshold,
                "query_keywords": 0,
                "mean_coverage": 0.0,
                "elapsed_ms": round((time.monotonic() - t0) * 1000, 2),
                "skipped": True,
            }
            logger.debug("MCA gate skipped: no query keywords")
            return candidates, stats

        filtered = []
        coverages = []

        for candidate in candidates:
            content = candidate.get("content", "")
            memory_keywords = extract_keywords(content)
            coverage = compute_coverage(query_keywords, memory_keywords)
            coverages.append(coverage)

            if coverage >= effective_threshold:
                candidate["mca_coverage"] = round(coverage, 4)
                filtered.append(candidate)

        elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
        mean_coverage = sum(coverages) / len(coverages) if coverages else 0.0

        stats = {
            "candidates_in": len(candidates),
            "candidates_out": len(filtered),
            "filtered_out": len(candidates) - len(filtered),
            "threshold": effective_threshold,
            "query_keywords": len(query_keywords),
            "mean_coverage": round(mean_coverage, 4),
            "elapsed_ms": elapsed_ms,
            "skipped": False,
        }

        logger.debug(
            "MCA gate: %d -> %d candidates (threshold=%.2f, keywords=%d, %.1fms)",
            len(candidates), len(filtered), effective_threshold,
            len(query_keywords), elapsed_ms,
        )

        # Emit analytics event
        self._track_event(stats)

        return filtered, stats

    def _track_event(self, stats: dict) -> None:
        """Emit analytics event for MCA filtering."""
        try:
            from cairn.core import analytics
            tracker = analytics._analytics_tracker
            if tracker is not None:
                tracker.record(analytics.UsageEvent(
                    operation="mca_gate",
                    metadata=stats,
                ))
        except Exception:
            pass  # Analytics should never block the pipeline
