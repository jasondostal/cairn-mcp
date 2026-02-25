"""Tests for Makefile language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_MAKEFILE = '''CC = gcc
CFLAGS = -Wall -g
PREFIX ?= /usr/local

# Build the application
all: build test

build: $(SRC)
\t$(CC) $(CFLAGS) -o app $(SRC)

test:
\tpytest tests/

clean:
\trm -rf build/ dist/

.PHONY: all build test clean

include config.mk
'''


class TestMakefileParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_MAKEFILE, "makefile")
        assert result.ok
        assert result.language == "makefile"
        assert len(result.content_hash) == 64

    def test_variables_extracted(self):
        result = self.parser.parse_source(SAMPLE_MAKEFILE, "makefile")
        vars_ = [s for s in result.symbols if s.kind == "variable"]
        names = {s.name for s in vars_}
        assert "CC" in names
        assert "CFLAGS" in names
        assert "PREFIX" in names

    def test_targets_extracted(self):
        result = self.parser.parse_source(SAMPLE_MAKEFILE, "makefile")
        targets = [s for s in result.symbols if s.kind == "target"]
        names = {s.name for s in targets}
        assert "all" in names
        assert "build" in names
        assert "test" in names
        assert "clean" in names

    def test_phony_target(self):
        result = self.parser.parse_source(SAMPLE_MAKEFILE, "makefile")
        targets = [s for s in result.symbols if s.kind == "target"]
        names = {s.name for s in targets}
        assert ".PHONY" in names

    def test_include_directive(self):
        result = self.parser.parse_source(SAMPLE_MAKEFILE, "makefile")
        imports = {s.name for s in result.imports}
        assert "config.mk" in imports

    def test_target_signature(self):
        result = self.parser.parse_source(SAMPLE_MAKEFILE, "makefile")
        all_target = next(s for s in result.symbols if s.name == "all")
        assert "build" in all_target.signature
        assert "test" in all_target.signature

    def test_variable_signature(self):
        result = self.parser.parse_source(SAMPLE_MAKEFILE, "makefile")
        cc = next(s for s in result.symbols if s.name == "CC")
        assert "gcc" in cc.signature

    def test_target_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_MAKEFILE, "makefile")
        all_target = next(s for s in result.symbols if s.name == "all")
        assert all_target.docstring is not None
        assert "Build" in all_target.docstring

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_MAKEFILE, "makefile")
        cc = next(s for s in result.symbols if s.name == "CC")
        assert cc.start_line == 1

    def test_empty_file(self):
        result = self.parser.parse_source("", "makefile")
        assert result.ok
        assert len(result.symbols) == 0

    def test_simple_rule(self):
        result = self.parser.parse_source("all:\n\techo hello\n", "makefile")
        assert result.ok
        targets = [s for s in result.symbols if s.kind == "target"]
        assert len(targets) == 1
        assert targets[0].name == "all"
