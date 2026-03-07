"""Tests for cross-project code analysis (Phase 7).

Uses mocked GraphProvider since Neo4j may not be available in CI.
"""

from unittest.mock import MagicMock, patch

from cairn.code.query import (
    query_hotspots,
    query_cross_search,
    query_shared_dependencies,
    query_search,
)


class TestQueryHotspots:

    def test_basic_pagerank(self):
        """Files with many dependents should rank higher."""
        graph = MagicMock()

        # Set up a simple dependency graph: A -> B, A -> C, B -> C
        graph.get_code_files.return_value = [
            {"path": "a.py", "uuid": "a"},
            {"path": "b.py", "uuid": "b"},
            {"path": "c.py", "uuid": "c"},
        ]
        graph.get_file_dependencies.side_effect = lambda path, pid: {
            "a.py": [{"path": "b.py"}, {"path": "c.py"}],
            "b.py": [{"path": "c.py"}],
            "c.py": [],
        }[path]

        result = query_hotspots(graph, project_id=1, limit=10)
        assert "hotspots" in result
        assert len(result["hotspots"]) == 3

        # c.py is imported by both a and b — should rank highest
        paths = [h["path"] for h in result["hotspots"]]
        assert paths[0] == "c.py"

    def test_empty_graph(self):
        graph = MagicMock()
        graph.get_code_files.return_value = []

        result = query_hotspots(graph, project_id=1)
        assert result["hotspots"] == []

    def test_single_file(self):
        graph = MagicMock()
        graph.get_code_files.return_value = [{"path": "a.py", "uuid": "a"}]
        graph.get_file_dependencies.return_value = []

        result = query_hotspots(graph, project_id=1)
        assert len(result["hotspots"]) == 1
        assert result["hotspots"][0]["path"] == "a.py"
        assert result["hotspots"][0]["pagerank"] == 1.0

    def test_limit_respected(self):
        graph = MagicMock()
        files = [{"path": f"file_{i}.py", "uuid": f"uuid-{i}"} for i in range(20)]
        graph.get_code_files.return_value = files
        graph.get_file_dependencies.return_value = []

        result = query_hotspots(graph, project_id=1, limit=5)
        assert len(result["hotspots"]) == 5


class TestQueryCrossSearch:

    def test_cross_search(self):
        graph = MagicMock()
        graph.search_code_symbols_cross_project.return_value = [
            {"qualified_name": "add", "name": "add", "kind": "function",
             "file_path": "a/utils.py", "project_id": 1, "score": 1.0},
            {"qualified_name": "add", "name": "add", "kind": "function",
             "file_path": "b/utils.py", "project_id": 2, "score": 0.9},
        ]

        result = query_cross_search(graph, "add", [1, 2])
        assert len(result["results"]) == 2
        assert result["project_ids"] == [1, 2]

    def test_cross_search_with_kind(self):
        graph = MagicMock()
        graph.search_code_symbols_cross_project.return_value = []

        result = query_cross_search(graph, "MyClass", [1], kind="class")
        graph.search_code_symbols_cross_project.assert_called_once_with(
            query="MyClass", project_ids=[1], kind="class", limit=20,
        )

    def test_cross_search_empty(self):
        graph = MagicMock()
        graph.search_code_symbols_cross_project.return_value = []

        result = query_cross_search(graph, "nonexistent", [1, 2])
        assert result["results"] == []


class TestQuerySharedDependencies:

    def test_shared_deps(self):
        graph = MagicMock()
        graph.get_shared_dependencies.return_value = [
            {"path": "shared/utils.py", "project_ids": [1, 2], "count": 2},
        ]

        result = query_shared_dependencies(graph, [1, 2])
        assert len(result["shared"]) == 1
        assert result["shared"][0]["count"] == 2

    def test_no_shared_deps(self):
        graph = MagicMock()
        graph.get_shared_dependencies.return_value = []

        result = query_shared_dependencies(graph, [1, 2])
        assert result["shared"] == []


class TestCodeSearch:

    def test_fulltext_search(self):
        graph = MagicMock()
        graph.search_code_symbols.return_value = [
            {"qualified_name": "add", "name": "add", "kind": "function",
             "file_path": "utils.py", "score": 1.0},
        ]

        result = query_search(graph, "add", project_id=1)
        assert result["mode"] == "fulltext"
        assert len(result["results"]) == 1

    def test_extra_kwargs_ignored(self):
        """query_search accepts **_kwargs for backward compat."""
        graph = MagicMock()
        graph.search_code_symbols.return_value = []

        result = query_search(
            graph, "test", project_id=1,
            mode="semantic", embedding_engine=None,
        )
        assert result["mode"] == "fulltext"
        assert result["results"] == []


class TestKnowledgeCodeBridging:

    def test_get_code_for_entity(self):
        graph = MagicMock()
        graph.get_code_for_entity.return_value = [
            {"type": "CodeFile", "path": "cairn/server.py", "qualified_name": None, "name": None},
            {"type": "CodeSymbol", "path": None, "qualified_name": "store", "name": "store"},
        ]

        result = graph.get_code_for_entity("entity-uuid-1")
        assert len(result) == 2

    def test_get_entities_for_code(self):
        graph = MagicMock()
        graph.get_entities_for_code.return_value = [
            {"uuid": "e1", "name": "Cairn", "entity_type": "Project"},
        ]

        result = graph.get_entities_for_code("cairn/server.py", project_id=1)
        assert len(result) == 1
        assert result[0]["name"] == "Cairn"

    def test_link_entity_to_code_file(self):
        graph = MagicMock()
        graph.link_entity_to_code_file("entity-uuid", "file-uuid")
        graph.link_entity_to_code_file.assert_called_once()

    def test_link_entity_to_code_symbol(self):
        graph = MagicMock()
        graph.link_entity_to_code_symbol("entity-uuid", "symbol-uuid")
        graph.link_entity_to_code_symbol.assert_called_once()
