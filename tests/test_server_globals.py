"""Tests for _ServerGlobals proxy and _init_services wiring (ca-218)."""

import types
from unittest.mock import MagicMock


def _make_fake_module():
    """Create a fake module mimicking cairn.server's globals."""
    mod = types.ModuleType("fake_server")
    mod.db = None
    mod.config = None
    mod.memory_store = None
    mod.search_engine = None
    mod.work_item_manager = None
    mod.task_manager = None
    return mod


def test_server_globals_reads_live_state():
    """_ServerGlobals proxy must read live module attributes, not cached copies."""
    from cairn.server import _ServerGlobals

    mod = _make_fake_module()
    proxy = _ServerGlobals(mod)

    # Initially None
    assert proxy["db"] is None

    # Set a value — proxy must see it immediately
    sentinel = object()
    mod.db = sentinel
    assert proxy["db"] is sentinel


def test_server_globals_get_with_default():
    """proxy.get() returns default for missing attributes."""
    from cairn.server import _ServerGlobals

    mod = _make_fake_module()
    proxy = _ServerGlobals(mod)
    assert proxy.get("nonexistent", "fallback") == "fallback"
    assert proxy.get("db") is None  # exists but is None


def test_server_globals_keyerror_on_missing():
    """proxy[key] raises KeyError for attributes that don't exist on the module."""
    from cairn.server import _ServerGlobals
    import pytest

    mod = _make_fake_module()
    proxy = _ServerGlobals(mod)
    with pytest.raises(KeyError):
        proxy["totally_nonexistent_attr"]


def test_init_services_populates_globals():
    """After _init_services(svc), the module globals must be non-None."""
    from cairn.server import _ServerGlobals, _init_services

    svc = MagicMock()
    svc.db = MagicMock(name="db")
    svc.config = MagicMock(name="config")
    svc.memory_store = MagicMock(name="memory_store")
    svc.search_engine = MagicMock(name="search_engine")
    svc.work_item_manager = MagicMock(name="work_item_manager")
    svc.task_manager = MagicMock(name="task_manager")

    _init_services(svc)

    # Now import the module and verify via proxy
    import cairn.server as server_mod
    proxy = _ServerGlobals(server_mod)

    assert proxy["db"] is svc.db
    assert proxy["memory_store"] is svc.memory_store
    assert proxy["search_engine"] is svc.search_engine
    assert proxy["config"] is svc.config


def test_init_services_raises_on_none_critical():
    """_init_services must raise if critical services are None (ca-211)."""
    import pytest

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
