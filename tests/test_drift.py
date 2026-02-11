"""Test drift detection: hash matching, project filtering, missing hashes."""

import json
from unittest.mock import MagicMock

from cairn.core.drift import DriftDetector


def _make_db_rows(rows):
    """Create a mock DB that returns the given rows."""
    db = MagicMock()
    db.execute.return_value = rows
    return db


# ── Empty / no files ─────────────────────────────────────────


def test_check_no_files():
    """check() with no files should return empty result."""
    db = _make_db_rows([])
    dd = DriftDetector(db)
    result = dd.check(files=None)
    assert result["checked_files"] == 0
    assert result["stale_count"] == 0


def test_check_empty_files_list():
    """check() with empty files list should return empty result."""
    db = _make_db_rows([])
    dd = DriftDetector(db)
    result = dd.check(files=[])
    assert result["checked_files"] == 0


def test_check_files_with_no_path():
    """Files without path/hash should be skipped."""
    db = _make_db_rows([])
    dd = DriftDetector(db)
    result = dd.check(files=[{"foo": "bar"}])
    assert result["checked_files"] == 0


# ── Hash matching ─────────────────────────────────────────────


def test_stale_memory_detected():
    """Memory with different hash should be flagged as stale."""
    rows = [
        {
            "id": 1,
            "summary": "Test memory",
            "memory_type": "code-snippet",
            "importance": 0.8,
            "file_hashes": {"src/main.py": "abc123"},
            "related_files": ["src/main.py"],
            "project": "cairn",
        }
    ]
    db = _make_db_rows(rows)
    dd = DriftDetector(db)

    result = dd.check(files=[
        {"path": "src/main.py", "hash": "def456"},
    ])

    assert result["stale_count"] == 1
    assert result["clean_count"] == 0
    assert result["checked_files"] == 1
    stale = result["stale_memories"][0]
    assert stale["id"] == 1
    assert stale["changed_files"][0]["stored_hash"] == "abc123"
    assert stale["changed_files"][0]["current_hash"] == "def456"


def test_clean_memory_not_flagged():
    """Memory with matching hash should not be flagged."""
    rows = [
        {
            "id": 1,
            "summary": "Test memory",
            "memory_type": "code-snippet",
            "importance": 0.8,
            "file_hashes": {"src/main.py": "abc123"},
            "related_files": ["src/main.py"],
            "project": "cairn",
        }
    ]
    db = _make_db_rows(rows)
    dd = DriftDetector(db)

    result = dd.check(files=[
        {"path": "src/main.py", "hash": "abc123"},
    ])

    assert result["stale_count"] == 0
    assert result["clean_count"] == 1


def test_multiple_files_partial_drift():
    """Memory tracking 2 files where only 1 drifted should be flagged."""
    rows = [
        {
            "id": 1,
            "summary": "Multi-file memory",
            "memory_type": "code-snippet",
            "importance": 0.7,
            "file_hashes": {
                "src/main.py": "abc123",
                "src/utils.py": "xyz789",
            },
            "related_files": ["src/main.py", "src/utils.py"],
            "project": "cairn",
        }
    ]
    db = _make_db_rows(rows)
    dd = DriftDetector(db)

    result = dd.check(files=[
        {"path": "src/main.py", "hash": "abc123"},
        {"path": "src/utils.py", "hash": "CHANGED"},
    ])

    assert result["stale_count"] == 1
    stale = result["stale_memories"][0]
    assert len(stale["changed_files"]) == 1
    assert stale["changed_files"][0]["path"] == "src/utils.py"


# ── String-encoded hashes ────────────────────────────────────


def test_string_encoded_file_hashes():
    """file_hashes stored as JSON string (not dict) should be parsed."""
    rows = [
        {
            "id": 2,
            "summary": "String hash memory",
            "memory_type": "note",
            "importance": 0.5,
            "file_hashes": json.dumps({"src/a.py": "hash1"}),
            "related_files": [],
            "project": "test",
        }
    ]
    db = _make_db_rows(rows)
    dd = DriftDetector(db)

    result = dd.check(files=[{"path": "src/a.py", "hash": "hash2"}])
    assert result["stale_count"] == 1


# ── Project filtering ─────────────────────────────────────────


def test_project_filter_in_query():
    """When project is provided, it should appear in the SQL query params."""
    db = MagicMock()
    db.execute.return_value = []
    dd = DriftDetector(db)

    dd.check(project="myproject", files=[{"path": "x.py", "hash": "h"}])

    call_args = db.execute.call_args
    # The params should contain 'myproject'
    params = call_args[0][1]
    assert "myproject" in params


# ── Result shape ──────────────────────────────────────────────


def test_result_shape():
    """Result should always have the four expected keys."""
    db = _make_db_rows([])
    dd = DriftDetector(db)
    result = dd.check(files=[{"path": "x.py", "hash": "h"}])
    assert set(result.keys()) == {"checked_files", "stale_memories", "clean_count", "stale_count"}


def test_stale_memory_shape():
    """Stale memory entries should have expected fields."""
    rows = [
        {
            "id": 10,
            "summary": "Test",
            "memory_type": "note",
            "importance": 0.5,
            "file_hashes": {"a.py": "old"},
            "related_files": [],
            "project": "test",
        }
    ]
    db = _make_db_rows(rows)
    dd = DriftDetector(db)

    result = dd.check(files=[{"path": "a.py", "hash": "new"}])
    stale = result["stale_memories"][0]
    assert "id" in stale
    assert "summary" in stale
    assert "memory_type" in stale
    assert "importance" in stale
    assert "project" in stale
    assert "changed_files" in stale
