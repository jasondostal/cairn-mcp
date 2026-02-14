"""Context budget utilities for MCP tool response size management.

Token estimation, truncation, and list budget enforcement. Used by server.py
to cap tool responses and by workspace.py to allocate context budgets.
"""

from __future__ import annotations

import json
from typing import Any

# Approximate tokens per whitespace-delimited word.
# Empirically ~1.3 for English text with code mixed in.
TOKENS_PER_WORD = 1.3


def estimate_tokens(text: str) -> int:
    """Estimate token count from text using word-count heuristic."""
    if not text:
        return 0
    return int(len(text.split()) * TOKENS_PER_WORD)


def estimate_tokens_for_dict(data: Any) -> int:
    """Estimate token count for a dict/list by JSON-serializing first."""
    try:
        text = json.dumps(data, default=str)
    except (TypeError, ValueError):
        text = str(data)
    return estimate_tokens(text)


def truncate_to_budget(
    text: str,
    budget_tokens: int,
    suffix: str = "...",
) -> str:
    """Truncate text to fit within a token budget, breaking at word boundaries.

    Returns the original text if it fits, otherwise truncates and appends suffix.
    """
    if budget_tokens <= 0:
        return text  # 0 = disabled
    if estimate_tokens(text) <= budget_tokens:
        return text

    words = text.split()
    # Target word count from token budget
    target_words = int(budget_tokens / TOKENS_PER_WORD)
    if target_words <= 0:
        return suffix

    truncated = " ".join(words[:target_words])
    return truncated + suffix


def apply_list_budget(
    items: list[dict],
    budget_tokens: int,
    content_key: str = "content",
    *,
    per_item_max: int = 0,
    overflow_message: str = "",
) -> tuple[list[dict], dict[str, Any]]:
    """Process a priority-sorted list, including items until budget is exhausted.

    Strategy: truncate individual item content before dropping items entirely.
    This preserves breadth (more items with shorter content) over depth.

    Args:
        items: Priority-sorted list of dicts (highest priority first).
        budget_tokens: Total token budget for the list. 0 = disabled (return all).
        content_key: Key in each dict containing the text content.
        per_item_max: Max tokens per individual item's content (0 = no per-item limit).
        overflow_message: Message template for overflow. Use {omitted} and {total} placeholders.

    Returns:
        Tuple of (included_items, metadata) where metadata contains:
        - total_available: total items in input
        - returned: items included in output
        - omitted: items dropped
        - overflow_message: formatted message if items were dropped, else empty
    """
    if budget_tokens <= 0:
        # Budget disabled — return everything unchanged
        return items, {
            "total_available": len(items),
            "returned": len(items),
            "omitted": 0,
            "overflow_message": "",
        }

    result: list[dict] = []
    tokens_used = 0

    for item in items:
        content = item.get(content_key, "")
        if not isinstance(content, str):
            content = str(content) if content is not None else ""

        # Per-item truncation first
        if per_item_max > 0:
            content = truncate_to_budget(content, per_item_max)

        item_tokens = estimate_tokens_for_dict(
            {k: (content if k == content_key else v) for k, v in item.items()}
        )

        if tokens_used + item_tokens > budget_tokens and result:
            # Budget exceeded — stop adding items
            break

        # Apply truncated content
        if per_item_max > 0 and content != item.get(content_key, ""):
            item = {**item, content_key: content}

        tokens_used += item_tokens
        result.append(item)

    omitted = len(items) - len(result)
    meta: dict[str, Any] = {
        "total_available": len(items),
        "returned": len(result),
        "omitted": omitted,
        "overflow_message": "",
    }

    if omitted > 0 and overflow_message:
        meta["overflow_message"] = overflow_message.format(
            omitted=omitted, total=len(items),
        )

    return result, meta
