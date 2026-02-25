"""Tests for JSON language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_JSON = '''{
  "name": "cairn",
  "version": 1,
  "description": "Persistent memory for agents",
  "tags": ["memory", "search", "ai"],
  "database": {
    "host": "localhost",
    "port": 5432
  },
  "enabled": true,
  "ratio": 3.14
}
'''


class TestJsonParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_JSON, "json")
        assert result.ok
        assert result.language == "json"
        assert len(result.content_hash) == 64

    def test_top_level_keys_extracted(self):
        result = self.parser.parse_source(SAMPLE_JSON, "json")
        names = {s.name for s in result.symbols}
        assert "name" in names
        assert "version" in names
        assert "description" in names
        assert "tags" in names
        assert "database" in names
        assert "enabled" in names
        assert "ratio" in names

    def test_key_count(self):
        result = self.parser.parse_source(SAMPLE_JSON, "json")
        assert len(result.symbols) == 7

    def test_nested_keys_not_extracted(self):
        result = self.parser.parse_source(SAMPLE_JSON, "json")
        names = {s.name for s in result.symbols}
        assert "host" not in names
        assert "port" not in names

    def test_symbol_kind(self):
        result = self.parser.parse_source(SAMPLE_JSON, "json")
        assert all(s.kind == "key" for s in result.symbols)

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_JSON, "json")
        name_sym = next(s for s in result.symbols if s.name == "name")
        assert name_sym.start_line > 0
        assert name_sym.end_line >= name_sym.start_line

    def test_docstring_is_none(self):
        result = self.parser.parse_source(SAMPLE_JSON, "json")
        assert all(s.docstring is None for s in result.symbols)

    def test_signature(self):
        result = self.parser.parse_source(SAMPLE_JSON, "json")
        name_sym = next(s for s in result.symbols if s.name == "name")
        assert name_sym.signature == "name"

    def test_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_JSON, "json")
        name_sym = next(s for s in result.symbols if s.name == "version")
        assert name_sym.qualified_name == "version"

    def test_no_imports(self):
        result = self.parser.parse_source(SAMPLE_JSON, "json")
        assert len(result.imports) == 0

    def test_empty_object(self):
        result = self.parser.parse_source("{}", "json")
        assert result.ok
        assert len(result.symbols) == 0

    def test_empty_file(self):
        result = self.parser.parse_source("", "json")
        assert result.ok
        assert len(result.symbols) == 0

    def test_array_root(self):
        result = self.parser.parse_source('[1, 2, 3]', "json")
        assert result.ok
        assert len(result.symbols) == 0

    def test_single_key(self):
        result = self.parser.parse_source('{"only": true}', "json")
        assert result.ok
        assert len(result.symbols) == 1
        assert result.symbols[0].name == "only"
