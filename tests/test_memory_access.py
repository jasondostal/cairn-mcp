"""Tests for MemoryAccessListener — access tracking via event bus."""

from unittest.mock import MagicMock, call

from cairn.listeners.memory_access import MemoryAccessListener


class TestMemoryAccessListener:

    def _make_listener(self):
        db = MagicMock()
        listener = MemoryAccessListener(db)
        return listener, db

    def test_register_subscribes_to_both_events(self):
        listener, _ = self._make_listener()
        event_bus = MagicMock()
        listener.register(event_bus)
        assert event_bus.subscribe.call_count == 2
        call_args = [c[0] for c in event_bus.subscribe.call_args_list]
        event_types = {args[0] for args in call_args}
        assert "search.executed" in event_types
        assert "memory.recalled" in event_types

    def test_handle_bumps_access_count(self):
        listener, db = self._make_listener()
        event = {
            "event_type": "search.executed",
            "payload": {"memory_ids": [1, 2, 3]},
        }
        listener.handle(event)
        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "access_count = access_count + 1" in sql
        assert "last_accessed_at = NOW()" in sql
        db.commit.assert_called_once()

    def test_handle_empty_memory_ids_is_noop(self):
        listener, db = self._make_listener()
        event = {
            "event_type": "search.executed",
            "payload": {"memory_ids": []},
        }
        listener.handle(event)
        db.execute.assert_not_called()

    def test_handle_missing_payload_is_noop(self):
        listener, db = self._make_listener()
        event = {"event_type": "search.executed"}
        listener.handle(event)
        db.execute.assert_not_called()

    def test_handle_none_payload_is_noop(self):
        listener, db = self._make_listener()
        event = {"event_type": "search.executed", "payload": None}
        listener.handle(event)
        db.execute.assert_not_called()

    def test_handle_db_error_rolls_back(self):
        listener, db = self._make_listener()
        db.execute.side_effect = Exception("connection lost")
        event = {
            "event_type": "memory.recalled",
            "payload": {"memory_ids": [1]},
        }
        # Should not raise
        listener.handle(event)
        db.rollback.assert_called_once()

    def test_handle_passes_correct_ids(self):
        listener, db = self._make_listener()
        event = {
            "event_type": "memory.recalled",
            "payload": {"memory_ids": [10, 20, 30]},
        }
        listener.handle(event)
        params = db.execute.call_args[0][1]
        assert params == (10, 20, 30)
