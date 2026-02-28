"""Tests for multi-agent anti-pattern detection (ca-154)."""

from __future__ import annotations

import pytest

from cairn.core.antipatterns import (
    AntiPatternFinding,
    analyze_epic,
    detect_drifting_anchorage,
    detect_skeleton_crew,
    detect_split_keel,
    extract_file_paths,
)


class TestExtractFilePaths:
    """Test file path extraction from task descriptions."""

    def test_basic_path(self):
        assert "config.py" in extract_file_paths("Modify config.py to add new setting")

    def test_nested_path(self):
        paths = extract_file_paths("Edit cairn/core/agents.py for new definitions")
        assert "cairn/core/agents.py" in paths

    def test_multiple_paths(self):
        text = "Update cairn/api/events.py and cairn/core/workspace.py"
        paths = extract_file_paths(text)
        assert "cairn/api/events.py" in paths
        assert "cairn/core/workspace.py" in paths

    def test_backtick_wrapped(self):
        paths = extract_file_paths("Modify `config.py` for settings")
        assert "config.py" in paths

    def test_tsx_extension(self):
        paths = extract_file_paths("Create sidebar-nav.tsx component")
        assert "sidebar-nav.tsx" in paths

    def test_no_paths(self):
        assert extract_file_paths("Add authentication feature") == set()

    def test_empty_string(self):
        assert extract_file_paths("") == set()

    def test_none_input(self):
        assert extract_file_paths(None) == set()


class TestSplitKeel:
    """Test Split Keel detection — two agents on the same file."""

    def test_no_conflict(self):
        children = [
            {"display_id": "ca-1", "title": "Edit config.py", "description": "Modify config.py", "status": "in_progress"},
            {"display_id": "ca-2", "title": "Edit routes.py", "description": "Modify routes.py", "status": "in_progress"},
        ]
        findings = detect_split_keel(children)
        assert len(findings) == 0

    def test_same_file_conflict(self):
        children = [
            {"display_id": "ca-1", "title": "Add auth to config.py", "description": "Modify config.py for auth", "status": "in_progress"},
            {"display_id": "ca-2", "title": "Add logging to config.py", "description": "Update config.py for logging", "status": "open"},
        ]
        findings = detect_split_keel(children)
        assert len(findings) == 1
        assert findings[0].pattern == "split_keel"
        assert "ca-1" in findings[0].affected_items
        assert "ca-2" in findings[0].affected_items
        assert "config.py" in findings[0].message

    def test_done_items_excluded(self):
        children = [
            {"display_id": "ca-1", "title": "Edit config.py", "description": "Modify config.py", "status": "done"},
            {"display_id": "ca-2", "title": "Also edit config.py", "description": "Update config.py", "status": "in_progress"},
        ]
        findings = detect_split_keel(children)
        assert len(findings) == 0  # done item doesn't conflict

    def test_multiple_conflicts(self):
        children = [
            {"display_id": "ca-1", "title": "Edit config.py and routes.py", "description": "Modify config.py routes.py", "status": "open"},
            {"display_id": "ca-2", "title": "Also edit config.py", "description": "Update config.py", "status": "open"},
            {"display_id": "ca-3", "title": "Also edit routes.py", "description": "Modify routes.py", "status": "in_progress"},
        ]
        findings = detect_split_keel(children)
        assert len(findings) == 2  # config.py and routes.py both conflict


class TestDriftingAnchorage:
    """Test Drifting Anchorage — scope creep detection."""

    def test_no_drift(self):
        children = [{"display_id": f"ca-{i}"} for i in range(5)]
        findings = detect_drifting_anchorage(children, original_count=5)
        assert len(findings) == 0

    def test_mild_growth_ok(self):
        children = [{"display_id": f"ca-{i}"} for i in range(6)]
        findings = detect_drifting_anchorage(children, original_count=5)
        assert len(findings) == 0  # 1.2x is under 1.5x threshold

    def test_significant_drift(self):
        children = [{"display_id": f"ca-{i}"} for i in range(10)]
        findings = detect_drifting_anchorage(children, original_count=5)
        assert any(f.pattern == "drifting_anchorage" for f in findings)
        assert "2.0x" in findings[0].message

    def test_custom_threshold(self):
        children = [{"display_id": f"ca-{i}"} for i in range(6)]
        findings = detect_drifting_anchorage(children, original_count=5, drift_threshold=1.1)
        assert len(findings) == 1  # 1.2x exceeds 1.1x

    def test_no_original_count(self):
        children = [{"display_id": f"ca-{i}"} for i in range(5)]
        findings = detect_drifting_anchorage(children, original_count=None)
        assert len(findings) == 0  # Can't detect drift without baseline

    def test_high_count_warning(self):
        children = [{"display_id": f"ca-{i}"} for i in range(12)]
        findings = detect_drifting_anchorage(children, original_count=None)
        assert len(findings) == 1
        assert "12 subtasks" in findings[0].message

    def test_zero_original_no_crash(self):
        children = [{"display_id": "ca-1"}]
        findings = detect_drifting_anchorage(children, original_count=0)
        assert len(findings) == 0  # Division by zero avoided


class TestSkeletonCrew:
    """Test Skeleton Crew — over-decomposition detection."""

    def test_no_trivial_tasks(self):
        children = [
            {"display_id": "ca-1", "title": "Implement authentication system",
             "description": "Build JWT auth with refresh tokens, bcrypt hashing, and middleware integration"},
            {"display_id": "ca-2", "title": "Build user registration flow",
             "description": "Create registration endpoint with email verification and password validation"},
        ]
        findings = detect_skeleton_crew(children)
        assert len(findings) == 0

    def test_trivial_tasks_detected(self):
        children = [
            {"display_id": "ca-1", "title": "Fix typo", "description": "Fix typo"},
            {"display_id": "ca-2", "title": "Add import", "description": "Add import"},
            {"display_id": "ca-3", "title": "Implement auth",
             "description": "Full authentication system with JWT, refresh tokens, and middleware"},
        ]
        findings = detect_skeleton_crew(children)
        assert len(findings) == 1
        assert findings[0].pattern == "skeleton_crew"
        assert "ca-1" in findings[0].affected_items
        assert "ca-2" in findings[0].affected_items
        assert "ca-3" not in findings[0].affected_items

    def test_single_trivial_not_flagged(self):
        """One trivial task is not enough — need 2+ to be a pattern."""
        children = [
            {"display_id": "ca-1", "title": "Fix typo", "description": "Fix typo"},
            {"display_id": "ca-2", "title": "Build feature",
             "description": "Complex feature with multiple components and tests"},
        ]
        findings = detect_skeleton_crew(children)
        assert len(findings) == 0


class TestAnalyzeEpic:
    """Test the combined analysis function."""

    def test_healthy_epic(self):
        children = [
            {"display_id": "ca-1", "title": "Implement auth module",
             "description": "Full auth system with JWT, bcrypt, middleware", "status": "done"},
            {"display_id": "ca-2", "title": "Build registration flow",
             "description": "Create registration with email verification and validation", "status": "done"},
            {"display_id": "ca-3", "title": "Add session management",
             "description": "Session handling with Redis backend and automatic expiry", "status": "in_progress"},
        ]
        result = analyze_epic(children, original_count=3)

        assert result["health"] == "healthy"
        assert result["error_count"] == 0
        assert result["warning_count"] == 0
        assert len(result["patterns_checked"]) == 3

    def test_caution_epic(self):
        children = [
            {"display_id": "ca-1", "title": "Edit config.py",
             "description": "Modify config.py for auth settings", "status": "in_progress"},
            {"display_id": "ca-2", "title": "Also edit config.py",
             "description": "Update config.py for logging settings", "status": "open"},
        ]
        result = analyze_epic(children, original_count=2)

        assert result["health"] == "caution"
        assert result["warning_count"] >= 1
        assert any(f["pattern"] == "split_keel" for f in result["findings"])

    def test_multiple_patterns(self):
        children = [
            {"display_id": "ca-1", "title": "Fix typo", "description": "Fix typo", "status": "open"},
            {"display_id": "ca-2", "title": "Add comma", "description": "Add comma", "status": "open"},
        ] + [
            {"display_id": f"ca-{i}", "title": f"Task {i}",
             "description": f"Task {i} with enough detail to not be trivial and pass the skeleton crew check",
             "status": "open"}
            for i in range(3, 15)
        ]
        result = analyze_epic(children, original_count=3)

        patterns_found = {f["pattern"] for f in result["findings"]}
        assert "skeleton_crew" in patterns_found
        assert "drifting_anchorage" in patterns_found

    def test_finding_to_dict(self):
        finding = AntiPatternFinding(
            pattern="split_keel",
            severity="warning",
            message="Conflict on config.py",
            affected_items=["ca-1", "ca-2"],
            recommendation="Sequence the tasks",
        )
        d = finding.to_dict()
        assert d["pattern"] == "split_keel"
        assert d["severity"] == "warning"
        assert d["affected_items"] == ["ca-1", "ca-2"]
