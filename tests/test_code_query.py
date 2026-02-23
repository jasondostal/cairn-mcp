"""Tests for the code query engine (structural queries over the code graph).

Uses mock GraphProvider since Neo4j may not be available in CI.
"""

from unittest.mock import MagicMock

from cairn.code.query import (
    _resolve_file_path,
    query_dependents,
    query_dependencies,
    query_impact,
    query_search,
    query_structure,
)


def _make_mock_graph():
    """Mock GraphProvider with reasonable defaults for query tests."""
    graph = MagicMock()
    graph.get_code_file.return_value = None
    graph.get_file_dependents.return_value = []
    graph.get_file_dependencies.return_value = []
    graph.get_file_structure.return_value = []
    graph.get_impact_graph.return_value = []
    graph.search_code_symbols.return_value = []
    return graph


# -- Target resolution --


class TestResolveFilePath:

    def test_file_path_found(self):
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "cairn/server.py"}
        assert _resolve_file_path(graph, "cairn/server.py", 1) == "cairn/server.py"

    def test_file_path_not_found(self):
        graph = _make_mock_graph()
        assert _resolve_file_path(graph, "does/not/exist.py", 1) is None

    def test_symbol_name_resolved(self):
        graph = _make_mock_graph()
        graph.search_code_symbols.return_value = [
            {"qualified_name": "MyClass.method", "file_path": "cairn/core.py"}
        ]
        assert _resolve_file_path(graph, "MyClass.method", 1) == "cairn/core.py"

    def test_symbol_name_not_found(self):
        graph = _make_mock_graph()
        assert _resolve_file_path(graph, "NonExistent", 1) is None

    def test_py_extension_treated_as_file(self):
        """Strings ending in .py go through file path resolution, not symbol search."""
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "setup.py"}
        result = _resolve_file_path(graph, "setup.py", 1)
        assert result == "setup.py"
        graph.search_code_symbols.assert_not_called()


# -- Dependents --


class TestQueryDependents:

    def test_returns_dependents(self):
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "cairn/config.py"}
        graph.get_file_dependents.return_value = [
            {"path": "cairn/server.py", "language": "python"},
            {"path": "cairn/core/search.py", "language": "python"},
        ]

        result = query_dependents(graph, "cairn/config.py", 1)
        assert result["target"] == "cairn/config.py"
        assert len(result["files"]) == 2
        assert "error" not in result

    def test_target_not_found(self):
        graph = _make_mock_graph()
        result = query_dependents(graph, "missing.py", 1)
        assert result["files"] == []
        assert "error" in result

    def test_no_dependents(self):
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "cairn/leaf.py"}
        result = query_dependents(graph, "cairn/leaf.py", 1)
        assert result["files"] == []
        assert "error" not in result


# -- Dependencies --


class TestQueryDependencies:

    def test_returns_dependencies(self):
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "cairn/server.py"}
        graph.get_file_dependencies.return_value = [
            {"path": "cairn/config.py", "language": "python"},
        ]

        result = query_dependencies(graph, "cairn/server.py", 1)
        assert result["target"] == "cairn/server.py"
        assert len(result["files"]) == 1

    def test_target_not_found(self):
        graph = _make_mock_graph()
        result = query_dependencies(graph, "missing.py", 1)
        assert "error" in result


# -- Structure --


class TestQueryStructure:

    def test_flat_structure(self):
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "mod.py"}
        graph.get_file_structure.return_value = [
            {"name": "foo", "qualified_name": "foo", "kind": "function",
             "start_line": 1, "end_line": 3, "signature": "def foo()", "docstring": None,
             "parent_name": None},
            {"name": "bar", "qualified_name": "bar", "kind": "function",
             "start_line": 5, "end_line": 7, "signature": "def bar()", "docstring": None,
             "parent_name": None},
        ]

        result = query_structure(graph, "mod.py", 1)
        assert result["target"] == "mod.py"
        assert len(result["symbols"]) == 2
        assert result["symbols"][0]["name"] == "foo"

    def test_hierarchical_structure(self):
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "mod.py"}
        graph.get_file_structure.return_value = [
            {"name": "MyClass", "qualified_name": "MyClass", "kind": "class",
             "start_line": 1, "end_line": 10, "signature": "class MyClass",
             "docstring": "A class.", "parent_name": None},
            {"name": "method", "qualified_name": "MyClass.method", "kind": "method",
             "start_line": 3, "end_line": 5, "signature": "def method(self)",
             "docstring": None, "parent_name": "MyClass"},
        ]

        result = query_structure(graph, "mod.py", 1)
        assert len(result["symbols"]) == 1  # Only top-level
        cls = result["symbols"][0]
        assert cls["name"] == "MyClass"
        assert len(cls["children"]) == 1
        assert cls["children"][0]["name"] == "method"

    def test_target_not_found(self):
        graph = _make_mock_graph()
        result = query_structure(graph, "missing.py", 1)
        assert result["symbols"] == []
        assert "error" in result


# -- Impact --


class TestQueryImpact:

    def test_single_depth(self):
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "cairn/config.py"}
        graph.get_impact_graph.return_value = [
            {"path": "cairn/server.py", "language": "python", "depth": 1},
            {"path": "cairn/core/search.py", "language": "python", "depth": 1},
        ]

        result = query_impact(graph, "cairn/config.py", 1)
        assert result["target"] == "cairn/config.py"
        assert result["affected_files"] == 2
        assert len(result["layers"]) == 1
        assert result["layers"][0]["depth"] == 1
        assert len(result["layers"][0]["files"]) == 2

    def test_multi_depth(self):
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "cairn/config.py"}
        graph.get_impact_graph.return_value = [
            {"path": "cairn/server.py", "language": "python", "depth": 1},
            {"path": "tests/test_server.py", "language": "python", "depth": 2},
        ]

        result = query_impact(graph, "cairn/config.py", 1, max_depth=3)
        assert result["affected_files"] == 2
        assert len(result["layers"]) == 2
        assert result["layers"][0]["depth"] == 1
        assert result["layers"][1]["depth"] == 2

    def test_target_not_found(self):
        graph = _make_mock_graph()
        result = query_impact(graph, "missing.py", 1)
        assert result["affected_files"] == 0
        assert result["layers"] == []
        assert "error" in result

    def test_no_impact(self):
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "cairn/leaf.py"}
        result = query_impact(graph, "cairn/leaf.py", 1)
        assert result["affected_files"] == 0
        assert result["layers"] == []
        assert "error" not in result

    def test_depth_passed_to_graph(self):
        graph = _make_mock_graph()
        graph.get_code_file.return_value = {"uuid": "u1", "path": "cairn/config.py"}
        query_impact(graph, "cairn/config.py", 1, max_depth=5)
        graph.get_impact_graph.assert_called_once_with("cairn/config.py", 1, max_depth=5)


# -- Search --


class TestQuerySearch:

    def test_returns_results(self):
        graph = _make_mock_graph()
        graph.search_code_symbols.return_value = [
            {"qualified_name": "SearchEngine.search", "name": "search",
             "kind": "method", "file_path": "cairn/core/search.py",
             "signature": "def search(self, query)", "score": 2.5},
        ]

        result = query_search(graph, "search", 1)
        assert result["query"] == "search"
        assert len(result["results"]) == 1
        assert result["results"][0]["name"] == "search"

    def test_empty_results(self):
        graph = _make_mock_graph()
        result = query_search(graph, "nonexistent", 1)
        assert result["results"] == []

    def test_kind_filter(self):
        graph = _make_mock_graph()
        query_search(graph, "search", 1, kind="function")
        graph.search_code_symbols.assert_called_once_with(
            query="search", project_id=1, kind="function", limit=20,
        )

    def test_limit(self):
        graph = _make_mock_graph()
        query_search(graph, "search", 1, limit=5)
        graph.search_code_symbols.assert_called_once_with(
            query="search", project_id=1, kind=None, limit=5,
        )

    def test_empty_kind_becomes_none(self):
        """Empty string kind should be treated as None (no filter)."""
        graph = _make_mock_graph()
        query_search(graph, "search", 1, kind="")
        graph.search_code_symbols.assert_called_once_with(
            query="search", project_id=1, kind=None, limit=20,
        )
