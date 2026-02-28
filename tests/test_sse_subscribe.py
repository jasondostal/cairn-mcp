"""Tests for the SSE subscribe endpoint pattern matching logic."""

import fnmatch

import pytest


def _matches(event_type: str, pattern_list: list[str]) -> bool:
    """Mirror the logic in api_sse_subscribe."""
    return any(fnmatch.fnmatch(event_type, p) for p in pattern_list)


class TestSSEPatternMatching:
    """Test the fnmatch-based pattern matching used by /api/sse/subscribe."""

    def test_wildcard_all(self):
        assert _matches("work_item.completed", ["*"]) is True

    def test_wildcard_prefix(self):
        assert _matches("work_item.completed", ["work_item.*"]) is True

    def test_exact_match(self):
        assert _matches("work_item.completed", ["work_item.completed"]) is True

    def test_no_match(self):
        assert _matches("work_item.completed", ["notification.*"]) is False

    def test_multiple_patterns_any_match(self):
        assert _matches("notification.created", ["work_item.*", "notification.*"]) is True

    def test_multiple_patterns_none_match(self):
        assert _matches("memory.created", ["work_item.*", "notification.*"]) is False

    def test_empty_patterns_no_match(self):
        assert _matches("work_item.completed", []) is False

    def test_double_wildcard(self):
        """Single * matches anything in fnmatch."""
        assert _matches("deeply.nested.event.type", ["*"]) is True

    def test_partial_wildcard(self):
        assert _matches("work_item.gated", ["work_item.g*"]) is True
        assert _matches("work_item.completed", ["work_item.g*"]) is False

    def test_question_mark_wildcard(self):
        """fnmatch ? matches any single character."""
        assert _matches("work_item.gated", ["work_item.gate?"]) is True
        assert _matches("work_item.gates", ["work_item.gate?"]) is True
        assert _matches("work_item.gated_x", ["work_item.gate?"]) is False

    def test_deliverable_patterns(self):
        patterns = ["deliverable.*", "work_item.gated"]
        assert _matches("deliverable.created", patterns) is True
        assert _matches("deliverable.approved", patterns) is True
        assert _matches("work_item.gated", patterns) is True
        assert _matches("work_item.completed", patterns) is False

    def test_notification_pattern(self):
        patterns = ["notification.*"]
        assert _matches("notification.created", patterns) is True
        assert _matches("notification.updated", patterns) is True
        assert _matches("work_item.completed", patterns) is False


class TestPatternParsing:
    """Test that comma-separated pattern strings parse correctly."""

    def _parse(self, raw: str) -> list[str]:
        """Mirror the parsing logic in api_sse_subscribe."""
        return [p.strip() for p in raw.split(",") if p.strip()]

    def test_single_pattern(self):
        assert self._parse("work_item.*") == ["work_item.*"]

    def test_multiple_patterns(self):
        assert self._parse("work_item.*,notification.*") == ["work_item.*", "notification.*"]

    def test_whitespace_handling(self):
        assert self._parse(" work_item.* , notification.* ") == ["work_item.*", "notification.*"]

    def test_empty_string(self):
        assert self._parse("") == []

    def test_trailing_comma(self):
        assert self._parse("work_item.*,") == ["work_item.*"]

    def test_multiple_commas(self):
        assert self._parse("work_item.*,,notification.*") == ["work_item.*", "notification.*"]
