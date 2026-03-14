"""Shared tool operations for search, recall, and modify.

Both MCP tools (cairn/tools/memory.py) and chat tools (cairn/chat_tools.py)
delegate to these functions for the common validate -> service call -> budget
cap -> event emit pipeline.  Callers handle their own async/sync wrapping,
tracing, auth, and response formatting.

Part of ca-257: deduplicate chat_tools.py — delegate to service layer.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cairn.core.budget import apply_list_budget
from cairn.core.constants import (
    BUDGET_INSIGHTS_PER_ITEM,
    BUDGET_RECALL_PER_ITEM,
    BUDGET_SEARCH_PER_ITEM,
    MAX_CONTENT_SIZE,
    MAX_RECALL_IDS,
    VALID_MEMORY_TYPES,
    VALID_SEARCH_MODES,
    MemoryAction,
)
from cairn.core.utils import validate_search

if TYPE_CHECKING:
    from cairn.core.services import Services

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------

def budgeted_search(
    svc: Services,
    *,
    query: str,
    project: str | None = None,
    memory_type: str | None = None,
    search_mode: str = "semantic",
    limit: int = 10,
    include_full: bool = False,
    as_of: str | None = None,
    event_after: str | None = None,
    event_before: str | None = None,
    ephemeral: bool | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Execute a search with budget caps, event emission, and confidence gating.

    Returns ``{"results": [...], "confidence": float | None}``.
    Results have budget caps applied and overflow markers appended.
    """
    validate_search(query, limit)
    if search_mode not in VALID_SEARCH_MODES:
        return {"error": f"invalid search_mode: {search_mode}. Must be one of: {', '.join(VALID_SEARCH_MODES)}"}

    results = svc.search_engine.search(
        query=query,
        project=project,
        memory_type=memory_type,
        search_mode=search_mode,
        limit=min(limit, 20),
        include_full=include_full,
        as_of=as_of,
        event_after=event_after,
        event_before=event_before,
        ephemeral=ephemeral,
    )

    # Budget cap
    budget = svc.config.budget.search
    if budget > 0 and results:
        content_key = "content" if include_full else "summary"
        results_capped, meta = apply_list_budget(
            results, budget, content_key,
            per_item_max=BUDGET_SEARCH_PER_ITEM,
            overflow_message=(
                "...{omitted} more results omitted. "
                "Use recall(ids=[...]) for full content, or narrow your query."
            ),
        )
        if meta["omitted"] > 0:
            results_capped.append({"_overflow": meta["overflow_message"]})
        results = results_capped

    # Event emission
    if svc.event_bus and results:
        try:
            memory_ids = [r["id"] for r in results if isinstance(r, dict) and "id" in r]
            payload: dict[str, Any] = {
                "query": query[:200],
                "result_count": len(memory_ids),
                "memory_ids": memory_ids[:20],
                "search_mode": search_mode,
            }
            if source:
                payload["source"] = source
            svc.event_bus.emit(
                "search.executed",
                project=project,
                payload=payload,
            )
        except Exception:
            logger.debug("Failed to publish search.executed event", exc_info=True)

    # Confidence gating
    confidence = svc.search_engine.assess_confidence(query, results)

    return {"results": results, "confidence": confidence}


# ------------------------------------------------------------------
# Recall
# ------------------------------------------------------------------

def budgeted_recall(
    svc: Services,
    *,
    ids: list[int],
    source: str | None = None,
) -> dict[str, Any]:
    """Recall memories by ID with budget caps and event emission.

    Returns ``{"results": [...]}`` or ``{"error": "..."}`` on validation failure.
    """
    if not ids:
        return {"error": "ids list is required and cannot be empty"}
    if len(ids) > MAX_RECALL_IDS:
        return {"error": f"Maximum {MAX_RECALL_IDS} IDs per recall. Batch into multiple calls."}

    results = svc.memory_store.recall(ids)

    # Budget cap
    budget = svc.config.budget.recall
    if budget > 0 and results:
        results_capped, meta = apply_list_budget(
            results, budget, "content",
            per_item_max=BUDGET_RECALL_PER_ITEM,
            overflow_message=(
                "...{omitted} memories truncated from response. "
                "Recall fewer IDs per call for full content."
            ),
        )
        if meta["omitted"] > 0:
            results_capped.append({"_overflow": meta["overflow_message"]})
        results = results_capped

    # Event emission
    if svc.event_bus and results:
        try:
            memory_ids = [r["id"] for r in results if isinstance(r, dict) and "id" in r]
            payload: dict[str, Any] = {
                "memory_ids": memory_ids,
                "count": len(memory_ids),
            }
            if source:
                payload["source"] = source
            svc.event_bus.emit(
                "memory.recalled",
                payload=payload,
            )
        except Exception:
            logger.debug("Failed to publish memory.recalled event", exc_info=True)

    return {"results": results}


# ------------------------------------------------------------------
# Modify validation
# ------------------------------------------------------------------

def validate_modify_inputs(
    action: str,
    content: str | None = None,
    memory_type: str | None = None,
    importance: float | None = None,
) -> str | None:
    """Validate modify inputs. Returns error string or None if valid."""
    if action not in MemoryAction.ALL:
        return f"invalid action: {action}. Must be one of: {', '.join(sorted(MemoryAction.ALL))}"
    if content is not None and len(content) > MAX_CONTENT_SIZE:
        return f"content exceeds {MAX_CONTENT_SIZE} character limit"
    if memory_type is not None and memory_type not in VALID_MEMORY_TYPES:
        return f"invalid memory_type: {memory_type}"
    if importance is not None and not (0.0 <= importance <= 1.0):
        return "importance must be between 0.0 and 1.0"
    return None


# ------------------------------------------------------------------
# Discover patterns
# ------------------------------------------------------------------

def budgeted_discover_patterns(
    svc: Services,
    *,
    project: str | None = None,
    topic: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Run pattern discovery with budget caps.

    Returns dict with status, cluster_count, clusters, last_clustered_at,
    and optional labeling_warning / _overflow.
    """
    ce = svc.cluster_engine
    reclustered = False
    labeling_error = None
    if ce.is_stale(project):
        cluster_result = ce.run_clustering(project)
        reclustered = True
        labeling_error = cluster_result.get("labeling_error")

    clusters = ce.get_clusters(
        project=project, topic=topic,
        min_confidence=0.5, limit=min(limit, 20),
    )
    last_run = ce.get_last_run(project)

    # Budget cap
    budget = svc.config.budget.insights
    overflow_msg = ""
    if budget > 0 and clusters:
        clusters, meta = apply_list_budget(
            clusters, budget, "summary",
            per_item_max=BUDGET_INSIGHTS_PER_ITEM,
            overflow_message=(
                "...{omitted} clusters omitted. "
                "Use a topic filter or increase limit for targeted results."
            ),
        )
        if meta["omitted"] > 0:
            overflow_msg = meta["overflow_message"]

    result: dict[str, Any] = {
        "status": "reclustered" if reclustered else "cached",
        "cluster_count": len(clusters),
        "clusters": clusters,
        "last_clustered_at": last_run["created_at"] if last_run else None,
    }
    if labeling_error:
        result["labeling_warning"] = labeling_error
    if overflow_msg:
        result["_overflow"] = overflow_msg
    return result
