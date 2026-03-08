"""Tests for _init_services validation (ca-218, updated for ca-237 DI refactor)."""

from unittest.mock import MagicMock

import pytest


def test_init_services_stores_svc():
    """After _init_services(svc), the module-level _svc must be set."""
    from cairn.server import _init_services

    svc = MagicMock()
    svc.db = MagicMock(name="db")
    svc.config = MagicMock(name="config")
    svc.memory_store = MagicMock(name="memory_store")
    svc.search_engine = MagicMock(name="search_engine")
    svc.work_item_manager = MagicMock(name="work_item_manager")
    svc.task_manager = MagicMock(name="task_manager")

    _init_services(svc)

    import cairn.server as server_mod
    assert server_mod._svc is svc


def test_init_services_raises_on_none_critical():
    """_init_services must raise if critical services are None (ca-211)."""
    from cairn.server import _init_services

    svc = MagicMock()
    svc.db = None  # Critical service is None
    svc.config = MagicMock()
    svc.memory_store = MagicMock()
    svc.search_engine = MagicMock()
    svc.work_item_manager = MagicMock()
    svc.task_manager = MagicMock()

    with pytest.raises(RuntimeError, match="db are None"):
        _init_services(svc)
