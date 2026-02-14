"""Tests for context budget utilities.

Tests the token estimation, truncation, and list budget functions
that control MCP tool response sizes.
"""

from cairn.core.budget import (
    TOKENS_PER_WORD,
    apply_list_budget,
    estimate_tokens,
    estimate_tokens_for_dict,
    truncate_to_budget,
)


# ============================================================
# estimate_tokens
# ============================================================

def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_single_word():
    assert estimate_tokens("hello") == int(1 * TOKENS_PER_WORD)


def test_estimate_tokens_sentence():
    text = "the quick brown fox jumps over the lazy dog"
    words = len(text.split())
    assert estimate_tokens(text) == int(words * TOKENS_PER_WORD)


def test_estimate_tokens_code():
    """Code with special chars should still estimate reasonably."""
    code = "def foo(x): return x * 2  # double"
    assert estimate_tokens(code) > 0


# ============================================================
# estimate_tokens_for_dict
# ============================================================

def test_estimate_tokens_for_dict_simple():
    data = {"key": "value", "number": 42}
    tokens = estimate_tokens_for_dict(data)
    assert tokens > 0


def test_estimate_tokens_for_dict_nested():
    data = {"items": [{"id": 1, "content": "hello world"}, {"id": 2, "content": "foo bar"}]}
    tokens = estimate_tokens_for_dict(data)
    assert tokens > estimate_tokens_for_dict({"key": "val"})


# ============================================================
# truncate_to_budget
# ============================================================

def test_truncate_fits_within_budget():
    """Text that fits should be returned unchanged."""
    text = "short text"
    result = truncate_to_budget(text, 100)
    assert result == text


def test_truncate_exceeds_budget():
    """Long text should be truncated with suffix."""
    words = ["word"] * 200
    text = " ".join(words)
    result = truncate_to_budget(text, 50)
    assert result.endswith("...")
    assert len(result) < len(text)


def test_truncate_budget_zero_disabled():
    """Budget of 0 should return text unchanged (disabled)."""
    text = "a " * 1000
    result = truncate_to_budget(text, 0)
    assert result == text


def test_truncate_custom_suffix():
    words = ["word"] * 200
    text = " ".join(words)
    result = truncate_to_budget(text, 50, suffix=" [truncated]")
    assert result.endswith("[truncated]")


def test_truncate_preserves_word_boundaries():
    """Truncation should not split words."""
    text = "hello world foo bar baz qux"
    result = truncate_to_budget(text, 3)  # very small budget
    # Should end with ... and contain complete words before that
    assert "..." in result
    parts = result.replace("...", "").strip().split()
    for part in parts:
        assert part in text.split()


# ============================================================
# apply_list_budget
# ============================================================

def _make_items(n: int, content_size: int = 50) -> list[dict]:
    """Create n items with predictable content."""
    return [
        {"id": i, "content": f"item {i} " + "x " * content_size, "type": "note"}
        for i in range(n)
    ]


def test_apply_list_budget_disabled():
    """Budget 0 should return all items unchanged."""
    items = _make_items(10)
    result, meta = apply_list_budget(items, 0, "content")
    assert len(result) == 10
    assert meta["omitted"] == 0
    assert meta["returned"] == 10
    assert meta["overflow_message"] == ""


def test_apply_list_budget_fits():
    """All items fit within a generous budget."""
    items = _make_items(3, content_size=5)
    result, meta = apply_list_budget(items, 10000, "content")
    assert len(result) == 3
    assert meta["omitted"] == 0


def test_apply_list_budget_truncates_list():
    """Tight budget should drop items from the tail."""
    items = _make_items(20, content_size=50)
    result, meta = apply_list_budget(items, 200, "content")
    assert len(result) < 20
    assert meta["omitted"] > 0
    assert meta["total_available"] == 20
    # First item should always be included (priority)
    assert result[0]["id"] == 0


def test_apply_list_budget_per_item_max():
    """Per-item max should truncate individual content before dropping."""
    items = [
        {"id": 0, "content": "word " * 500},  # ~650 tokens
        {"id": 1, "content": "word " * 500},
    ]
    result, meta = apply_list_budget(
        items, 500, "content", per_item_max=100,
    )
    # With per-item truncation, content should be shorter
    for item in result:
        assert estimate_tokens(item["content"]) <= 110  # ~100 + fudge


def test_apply_list_budget_overflow_message():
    """Overflow message should be formatted with counts."""
    items = _make_items(20, content_size=50)
    result, meta = apply_list_budget(
        items, 200, "content",
        overflow_message="...{omitted} of {total} items omitted.",
    )
    if meta["omitted"] > 0:
        assert str(meta["omitted"]) in meta["overflow_message"]
        assert str(meta["total_available"]) in meta["overflow_message"]


def test_apply_list_budget_empty_list():
    """Empty input should return empty output."""
    result, meta = apply_list_budget([], 1000, "content")
    assert result == []
    assert meta["total_available"] == 0
    assert meta["returned"] == 0


def test_apply_list_budget_preserves_priority_order():
    """Items should be returned in input order (priority-sorted)."""
    items = [
        {"id": "high", "content": "important rule", "importance": 0.9},
        {"id": "mid", "content": "medium rule", "importance": 0.5},
        {"id": "low", "content": "minor rule " * 100, "importance": 0.1},
    ]
    result, meta = apply_list_budget(items, 200, "content")
    assert result[0]["id"] == "high"
    if len(result) > 1:
        assert result[1]["id"] == "mid"


def test_apply_list_budget_first_item_always_included():
    """Even with a tiny budget, the first item should be included."""
    items = _make_items(5, content_size=100)
    result, meta = apply_list_budget(items, 1, "content")
    # First item is always included even if it exceeds budget
    assert len(result) >= 1
    assert result[0]["id"] == 0
