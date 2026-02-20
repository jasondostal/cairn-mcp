"""Tests for memory event publishing and async enrichment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from cairn.core.memory import MemoryStore


class TestMemoryEventPublishing:
    """Test that MemoryStore publishes events at the right times."""

    def _make_store(self, event_bus=None):
        db = MagicMock()
        embedding = MagicMock()
        embedding.embed.return_value = [0.1] * 10
        db.execute.return_value = []
        store = MemoryStore(
            db, embedding, event_bus=event_bus,
        )
        return store

    def _stub_store_calls(self, store, project_name="test-project"):
        """Stub db calls needed by store(): get_or_create_project, INSERT, _publish lookup."""
        created_at = MagicMock()
        created_at.isoformat.return_value = "2026-01-01T00:00:00"
        store.db.execute_one.side_effect = [
            {"id": 1},                              # get_or_create_project
            {"id": 42, "created_at": created_at},   # INSERT RETURNING
            {"name": project_name},                  # project name lookup in _publish
        ]

    def test_store_publishes_memory_created_when_event_bus(self):
        bus = MagicMock()
        bus.publish.return_value = 1
        store = self._make_store(event_bus=bus)
        self._stub_store_calls(store)

        store.store(content="hello", project="test-project")

        publish_calls = bus.publish.call_args_list
        assert len(publish_calls) >= 1
        event_call = publish_calls[0]
        assert event_call.kwargs["event_type"] == "memory.created"
        assert event_call.kwargs["payload"]["memory_id"] == 42

    def test_store_skips_phase2_when_event_bus(self):
        """When event_bus is present, Phase 2 enrichment is NOT run inline."""
        bus = MagicMock()
        bus.publish.return_value = 1
        store = self._make_store(event_bus=bus)
        self._stub_store_calls(store)

        with patch.object(store, "_post_store_enrichment") as mock_enrich:
            store.store(content="hello", project="test-project")
            mock_enrich.assert_not_called()

    def test_store_runs_phase2_inline_without_event_bus(self):
        """Without event_bus, Phase 2 enrichment runs inline (backward compat)."""
        store = self._make_store(event_bus=None)
        created_at = MagicMock()
        created_at.isoformat.return_value = "2026-01-01T00:00:00"
        store.db.execute_one.side_effect = [
            {"id": 1},                              # get_or_create_project
            {"id": 42, "created_at": created_at},   # INSERT RETURNING
        ]

        with patch.object(store, "_post_store_enrichment", return_value={}) as mock_enrich:
            store.store(content="hello", project="test-project")
            mock_enrich.assert_called_once()

    def test_modify_inactivate_publishes_event(self):
        bus = MagicMock()
        bus.publish.return_value = 1
        store = self._make_store(event_bus=bus)
        # execute_one calls: _get_memory_project_id, project name in _publish
        store.db.execute_one.side_effect = [
            {"project_id": 5},   # _get_memory_project_id
            {"name": "test"},    # project name lookup in _publish
        ]

        store.modify(memory_id=42, action="inactivate", reason="outdated")

        publish_calls = bus.publish.call_args_list
        assert len(publish_calls) >= 1
        assert publish_calls[0].kwargs["event_type"] == "memory.inactivated"

    def test_modify_update_publishes_event(self):
        bus = MagicMock()
        bus.publish.return_value = 1
        store = self._make_store(event_bus=bus)
        # execute_one calls: _get_memory_project_id, project name in _publish
        store.db.execute_one.side_effect = [
            {"project_id": 5},
            {"name": "test"},
        ]

        store.modify(memory_id=42, action="update", importance=0.9)

        publish_calls = bus.publish.call_args_list
        assert len(publish_calls) >= 1
        assert publish_calls[0].kwargs["event_type"] == "memory.updated"

    def test_no_events_without_event_bus(self):
        store = self._make_store(event_bus=None)
        created_at = MagicMock()
        created_at.isoformat.return_value = "2026-01-01T00:00:00"
        store.db.execute_one.side_effect = [
            {"id": 1},                            # get_or_create_project
            {"id": 42, "created_at": created_at},  # INSERT RETURNING
        ]
        with patch.object(store, "_post_store_enrichment", return_value={}):
            store.store(content="hello", project="test")
        # No event bus — _publish is a no-op. No crash.


class TestMemoryEnrichmentListener:
    """Test the MemoryEnrichmentListener event handler."""

    def test_register_subscribes_to_memory_events(self):
        from cairn.listeners.memory_enrichment import MemoryEnrichmentListener

        store = MagicMock()
        listener = MemoryEnrichmentListener(store)
        bus = MagicMock()

        listener.register(bus)

        bus.subscribe.assert_called_once_with("memory.*", "memory_enrichment", listener.handle)

    def test_handle_created_calls_post_store_enrichment(self):
        from cairn.listeners.memory_enrichment import MemoryEnrichmentListener

        store = MagicMock()
        store.db.execute_one.return_value = {
            "content": "test content",
            "embedding": [0.1] * 10,
            "session_name": "sess-1",
            "entities": ["Alice"],
            "project_name": "test",
        }
        listener = MemoryEnrichmentListener(store)

        event = {
            "event_type": "memory.created",
            "payload": {
                "memory_id": 42,
                "project_id": 1,
                "memory_type": "note",
                "enrich": True,
            },
            "session_name": "sess-1",
        }

        listener.handle(event)

        store._post_store_enrichment.assert_called_once()
        call_kwargs = store._post_store_enrichment.call_args.kwargs
        assert call_kwargs["memory_id"] == 42
        assert call_kwargs["project_id"] == 1
        assert call_kwargs["enrich"] is True

    def test_handle_inactivated_does_not_crash(self):
        from cairn.listeners.memory_enrichment import MemoryEnrichmentListener

        store = MagicMock()
        listener = MemoryEnrichmentListener(store)

        event = {
            "event_type": "memory.inactivated",
            "payload": {"memory_id": 42, "reason": "outdated"},
        }

        # Should not raise
        listener.handle(event)
