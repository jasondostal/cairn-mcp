"""Tests for the code indexer (parser → graph pipeline).

Uses mock GraphProvider since Neo4j may not be available in CI.
"""

from pathlib import Path
from unittest.mock import MagicMock, call

from cairn.code.parser import CodeParser
from cairn.code.indexer import CodeIndexer, IndexResult
from cairn.code.utils import path_to_module as _path_to_module


class TestPathToModule:

    def test_regular_file(self):
        assert _path_to_module("cairn/core/search.py") == "cairn.core.search"

    def test_init_file(self):
        assert _path_to_module("cairn/core/__init__.py") == "cairn.core"

    def test_top_level(self):
        assert _path_to_module("setup.py") == "setup"

    def test_non_python(self):
        assert _path_to_module("README.md") is None

    def test_nested(self):
        assert _path_to_module("cairn/code/languages/python.py") == "cairn.code.languages.python"


class TestIndexResult:

    def test_ok_when_no_errors(self):
        result = IndexResult(project="test", project_id=1)
        assert result.ok

    def test_not_ok_with_errors(self):
        result = IndexResult(project="test", project_id=1, errors=["bad"])
        assert not result.ok

    def test_summary(self):
        result = IndexResult(
            project="test", project_id=1,
            files_indexed=5, files_skipped=10, files_deleted=1,
            symbols_created=50, imports_created=20,
        )
        s = result.summary()
        assert "5 files" in s
        assert "10 unchanged" in s
        assert "50 symbols" in s


class TestCodeIndexer:

    def _make_mock_graph(self):
        """Create a mock GraphProvider with reasonable defaults."""
        graph = MagicMock()
        graph.get_code_file.return_value = None  # No existing files
        graph.get_code_files.return_value = []    # No stale files
        graph.batch_upsert_code_graph.return_value = {}  # path -> uuid
        # Keep old methods mocked for index_file fallback
        graph.ensure_code_file.return_value = "file-uuid-1"
        graph.ensure_code_symbol.return_value = "sym-uuid-1"
        return graph

    def test_index_single_file(self, tmp_path):
        (tmp_path / "hello.py").write_text("def hello(): pass\n")

        graph = self._make_mock_graph()
        parser = CodeParser()
        indexer = CodeIndexer(parser, graph)

        result = indexer.index_file(
            tmp_path / "hello.py", project="test", project_id=1
        )
        assert result.files_indexed == 1
        assert result.symbols_created == 1
        assert graph.batch_upsert_code_graph.called
        # Verify the batch call got the right file data
        call_args = graph.batch_upsert_code_graph.call_args
        files_arg = call_args.kwargs.get("files") or call_args[1].get("files", call_args[0][1] if len(call_args[0]) > 1 else None)
        if files_arg is None:
            # positional args: (project_id, files, import_edges, stale_file_uuids)
            files_arg = call_args.kwargs.get("files", [])
        assert len(files_arg) == 1
        assert files_arg[0]["language"] == "python"

    def test_skips_unchanged_file(self, tmp_path):
        (tmp_path / "hello.py").write_text("def hello(): pass\n")

        parser = CodeParser()
        # First, parse to get the hash
        parsed = parser.parse_file(tmp_path / "hello.py")

        graph = self._make_mock_graph()
        graph.get_code_file.return_value = {
            "uuid": "existing-uuid",
            "content_hash": parsed.content_hash,
        }

        indexer = CodeIndexer(parser, graph)
        result = indexer.index_file(
            tmp_path / "hello.py", project="test", project_id=1
        )
        assert result.files_skipped == 1
        assert result.files_indexed == 0
        assert not graph.batch_upsert_code_graph.called

    def test_reindexes_changed_file(self, tmp_path):
        (tmp_path / "hello.py").write_text("def hello(): pass\n")

        graph = self._make_mock_graph()
        graph.get_code_file.return_value = {
            "uuid": "existing-uuid",
            "content_hash": "old-hash-different",
        }

        parser = CodeParser()
        indexer = CodeIndexer(parser, graph)

        result = indexer.index_file(
            tmp_path / "hello.py", project="test", project_id=1
        )
        assert result.files_indexed == 1
        assert graph.batch_upsert_code_graph.called

    def test_force_reindexes(self, tmp_path):
        (tmp_path / "hello.py").write_text("def hello(): pass\n")

        parser = CodeParser()
        parsed = parser.parse_file(tmp_path / "hello.py")

        graph = self._make_mock_graph()
        graph.get_code_file.return_value = {
            "uuid": "existing-uuid",
            "content_hash": parsed.content_hash,  # Same hash
        }

        indexer = CodeIndexer(parser, graph)
        result = indexer.index_file(
            tmp_path / "hello.py", project="test", project_id=1, force=True
        )
        assert result.files_indexed == 1  # Forced re-index

    def test_index_directory(self, tmp_path):
        (tmp_path / "a.py").write_text("def a(): pass\n")
        (tmp_path / "b.py").write_text("class B: pass\n")
        (tmp_path / "readme.txt").write_text("Not indexed\n")

        graph = self._make_mock_graph()
        parser = CodeParser()
        indexer = CodeIndexer(parser, graph)

        result = indexer.index_directory(
            tmp_path, project="test", project_id=1
        )
        assert result.files_scanned == 2  # Only .py files
        assert result.files_indexed == 2
        # Should have made one batch call with both files
        assert graph.batch_upsert_code_graph.called
        call_kwargs = graph.batch_upsert_code_graph.call_args.kwargs
        assert len(call_kwargs["files"]) == 2

    def test_stale_file_cleanup(self, tmp_path):
        """Files in graph but not on disk should be deleted."""
        (tmp_path / "a.py").write_text("x = 1\n")

        graph = self._make_mock_graph()
        # Simulate a file that was previously indexed but no longer exists
        graph.get_code_files.return_value = [
            {"uuid": "stale-uuid", "path": str(tmp_path / "deleted.py"),
             "content_hash": "old", "language": "python", "last_indexed": "2024-01-01"},
        ]

        parser = CodeParser()
        indexer = CodeIndexer(parser, graph)

        result = indexer.index_directory(
            tmp_path, project="test", project_id=1
        )
        assert result.files_deleted == 1
        # Stale UUID should be passed to batch_upsert
        call_kwargs = graph.batch_upsert_code_graph.call_args.kwargs
        assert "stale-uuid" in call_kwargs["stale_file_uuids"]

    def test_class_method_symbols_in_batch(self, tmp_path):
        source = '''
class MyClass:
    def method(self):
        pass
'''
        (tmp_path / "mod.py").write_text(source)

        graph = self._make_mock_graph()
        parser = CodeParser()
        indexer = CodeIndexer(parser, graph)
        result = indexer.index_file(tmp_path / "mod.py", project="test", project_id=1)

        assert result.files_indexed == 1
        assert result.symbols_created >= 2  # class + method at minimum
        # Verify batch call includes both symbols with parent linkage
        call_kwargs = graph.batch_upsert_code_graph.call_args.kwargs
        file_data = call_kwargs["files"][0]
        names = [s["qualified_name"] for s in file_data["symbols"]]
        assert "MyClass" in names
        assert "MyClass.method" in names
        # Method should reference parent
        method_sym = [s for s in file_data["symbols"] if s["qualified_name"] == "MyClass.method"][0]
        assert method_sym["parent_name"] == "MyClass"

    def test_unsupported_file_ignored(self, tmp_path):
        (tmp_path / "data.xyz").write_text("not a supported format\n")

        graph = self._make_mock_graph()
        parser = CodeParser()
        indexer = CodeIndexer(parser, graph)

        result = indexer.index_file(
            tmp_path / "data.xyz", project="test", project_id=1
        )
        assert result.files_scanned == 1
        assert result.files_indexed == 0
        assert not graph.batch_upsert_code_graph.called
