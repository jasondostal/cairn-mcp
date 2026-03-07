"""Tests for orient() error surfacing behavior (ca-219)."""

from unittest.mock import MagicMock


def _make_config():
    """Create a minimal config mock with budget settings."""
    config = MagicMock()
    config.budget.orient = 6000
    return config


def test_orient_returns_errors_key_when_service_is_none():
    """When critical services are None, orient must return _errors, not empty arrays."""
    from cairn.core.orient import run_orient

    result = run_orient(
        project="test",
        config=_make_config(),
        db=None,
        memory_store=None,
        search_engine=None,
        work_item_manager=None,
        task_manager=None,
    )

    assert "_errors" in result, (
        "orient() returned no _errors key when all services were None — "
        "this is the silent failure bug"
    )
    assert len(result["_errors"]) > 0
    assert any("None" in e or "unavailable" in e.lower() for e in result["_errors"])


def test_orient_returns_errors_key_on_partial_none():
    """Even one critical None service should trigger _errors."""
    from cairn.core.orient import run_orient

    result = run_orient(
        project="test",
        config=_make_config(),
        db=MagicMock(),
        memory_store=None,  # just this one
        search_engine=MagicMock(),
        work_item_manager=MagicMock(),
        task_manager=MagicMock(),
    )

    assert "_errors" in result
    assert any("memory_store" in e for e in result["_errors"])


def test_orient_tracks_section_failures():
    """When a section raises, _errors must list the failed section."""
    from cairn.core.orient import run_orient

    memory_store = MagicMock()
    memory_store.get_rules.side_effect = RuntimeError("db connection lost")

    search_engine = MagicMock()
    search_engine.search.return_value = []

    db = MagicMock()
    db.execute.return_value = []

    work_item_manager = MagicMock()
    work_item_manager.ready_queue.return_value = {"items": []}
    work_item_manager.list_items.return_value = {"items": []}

    task_manager = MagicMock()
    task_manager.list_tasks.return_value = {"items": []}

    result = run_orient(
        project="test",
        config=_make_config(),
        db=db,
        memory_store=memory_store,
        search_engine=search_engine,
        work_item_manager=work_item_manager,
        task_manager=task_manager,
    )

    assert "_errors" in result
    assert "rules" in result["_errors"]


def test_orient_no_errors_on_healthy_boot():
    """When all services work, _errors should not be present."""
    from cairn.core.orient import run_orient

    memory_store = MagicMock()
    memory_store.get_rules.return_value = {"items": []}

    search_engine = MagicMock()
    search_engine.search.return_value = []

    db = MagicMock()
    db.execute.return_value = []

    work_item_manager = MagicMock()
    work_item_manager.ready_queue.return_value = {"items": []}
    work_item_manager.list_items.return_value = {"items": []}

    task_manager = MagicMock()
    task_manager.list_tasks.return_value = {"items": []}

    result = run_orient(
        project="test",
        config=_make_config(),
        db=db,
        memory_store=memory_store,
        search_engine=search_engine,
        work_item_manager=work_item_manager,
        task_manager=task_manager,
    )

    assert "_errors" not in result
    assert result["rules"] == []
    assert result["_budget"]["total"] == 6000
