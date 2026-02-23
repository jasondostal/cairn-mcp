"""Tests for CodeBridgeService — REFERENCED_IN edge creation."""

from unittest.mock import MagicMock

from cairn.code.bridge import CodeBridgeService


class TestBridgeAll:

    def test_calls_both_batch_methods(self):
        graph = MagicMock()
        graph.bridge_entities_to_symbols_batch.return_value = 3
        graph.bridge_entities_to_files_batch.return_value = 1

        svc = CodeBridgeService(graph)
        result = svc.bridge_all(project_id=42)

        graph.bridge_entities_to_symbols_batch.assert_called_once_with(42)
        graph.bridge_entities_to_files_batch.assert_called_once_with(42)
        assert result == {"symbol_edges": 3, "file_edges": 1, "total": 4}

    def test_zero_edges(self):
        graph = MagicMock()
        graph.bridge_entities_to_symbols_batch.return_value = 0
        graph.bridge_entities_to_files_batch.return_value = 0

        svc = CodeBridgeService(graph)
        result = svc.bridge_all(project_id=1)

        assert result["total"] == 0


class TestBridgeEntityNames:

    def test_calls_targeted_methods(self):
        graph = MagicMock()
        graph.bridge_entity_names_to_symbols.return_value = 2
        graph.bridge_entity_names_to_files.return_value = 0

        svc = CodeBridgeService(graph)
        result = svc.bridge_entity_names(["Neo4jGraphProvider", "server.py"], project_id=7)

        graph.bridge_entity_names_to_symbols.assert_called_once_with(
            ["Neo4jGraphProvider", "server.py"], 7,
        )
        graph.bridge_entity_names_to_files.assert_called_once_with(
            ["Neo4jGraphProvider", "server.py"], 7,
        )
        assert result == {"symbol_edges": 2, "file_edges": 0, "total": 2}

    def test_empty_names_skips_calls(self):
        graph = MagicMock()

        svc = CodeBridgeService(graph)
        result = svc.bridge_entity_names([], project_id=1)

        graph.bridge_entity_names_to_symbols.assert_not_called()
        graph.bridge_entity_names_to_files.assert_not_called()
        assert result["total"] == 0

    def test_no_matches(self):
        graph = MagicMock()
        graph.bridge_entity_names_to_symbols.return_value = 0
        graph.bridge_entity_names_to_files.return_value = 0

        svc = CodeBridgeService(graph)
        result = svc.bridge_entity_names(["NonExistent"], project_id=1)

        assert result["total"] == 0
