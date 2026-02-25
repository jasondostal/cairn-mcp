"""Tests for TOML language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_TOML = '''# Project metadata
name = "cairn"
version = "0.60.0"
description = "Persistent memory"

# Build configuration
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "cairn-mcp"
version = "0.60.0"

# Author information
[[project.authors]]
name = "John"
email = "john@example.com"
'''


class TestTomlParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        assert result.ok
        assert result.language == "toml"
        assert len(result.content_hash) == 64

    def test_top_level_keys_extracted(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        names = {s.name for s in result.symbols if s.kind == "key"}
        assert "name" in names
        assert "version" in names
        assert "description" in names

    def test_tables_extracted(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        tables = [s for s in result.symbols if s.kind == "table"]
        table_names = {s.name for s in tables}
        assert "build-system" in table_names
        assert "project" in table_names

    def test_table_array_extracted(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        tables = [s for s in result.symbols if s.kind == "table"]
        table_names = {s.name for s in tables}
        assert "project.authors" in table_names

    def test_table_signature(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        build = next(s for s in result.symbols if s.name == "build-system")
        assert build.signature == "[build-system]"

    def test_table_array_signature(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        authors = next(s for s in result.symbols if s.name == "project.authors")
        assert authors.signature == "[[project.authors]]"

    def test_key_signature(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        name_sym = next(s for s in result.symbols if s.name == "name" and s.kind == "key")
        assert "name" in name_sym.signature
        assert "cairn" in name_sym.signature

    def test_doc_comment_on_key(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        name_sym = next(s for s in result.symbols if s.name == "name" and s.kind == "key")
        assert name_sym.docstring == "Project metadata"

    def test_doc_comment_on_table(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        build = next(s for s in result.symbols if s.name == "build-system")
        assert build.docstring == "Build configuration"

    def test_doc_comment_on_table_array(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        authors = next(s for s in result.symbols if s.name == "project.authors")
        assert authors.docstring == "Author information"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        build = next(s for s in result.symbols if s.name == "build-system")
        assert build.start_line > 0
        assert build.end_line >= build.start_line

    def test_no_imports(self):
        result = self.parser.parse_source(SAMPLE_TOML, "toml")
        assert len(result.imports) == 0

    def test_empty_file(self):
        result = self.parser.parse_source("", "toml")
        assert result.ok
        assert len(result.symbols) == 0

    def test_minimal_toml(self):
        result = self.parser.parse_source('key = "value"\n', "toml")
        assert result.ok
        assert len(result.symbols) == 1
        assert result.symbols[0].name == "key"
        assert result.symbols[0].kind == "key"

    def test_table_only(self):
        source = '''[section]
key = "value"
'''
        result = self.parser.parse_source(source, "toml")
        assert result.ok
        tables = [s for s in result.symbols if s.kind == "table"]
        assert len(tables) == 1
        assert tables[0].name == "section"
