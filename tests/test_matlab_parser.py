"""Tests for MATLAB language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_MATLAB = '''function result = add(a, b)
% ADD adds two numbers together
    result = a + b;
end

function [x, y] = split(data)
    x = data(1);
    y = data(2);
end

function display(msg)
    fprintf("%s\\n", msg);
end
'''


class TestMatlabParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_MATLAB, "matlab")
        assert result.ok
        assert result.language == "matlab"
        assert len(result.content_hash) == 64

    def test_functions_extracted(self):
        result = self.parser.parse_source(SAMPLE_MATLAB, "matlab")
        funcs = [s for s in result.symbols if s.kind == "function"]
        names = {s.name for s in funcs}
        assert "add" in names
        assert "split" in names
        assert "display" in names

    def test_function_count(self):
        result = self.parser.parse_source(SAMPLE_MATLAB, "matlab")
        assert len(result.symbols) == 3

    def test_function_signature(self):
        result = self.parser.parse_source(SAMPLE_MATLAB, "matlab")
        add = next(s for s in result.symbols if s.name == "add")
        assert "function" in add.signature
        assert "result" in add.signature
        assert "add" in add.signature

    def test_multi_output_signature(self):
        result = self.parser.parse_source(SAMPLE_MATLAB, "matlab")
        split = next(s for s in result.symbols if s.name == "split")
        assert "function" in split.signature
        assert "split" in split.signature

    def test_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_MATLAB, "matlab")
        add = next(s for s in result.symbols if s.name == "add")
        assert add.docstring is not None
        assert "ADD" in add.docstring

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_MATLAB, "matlab")
        add = next(s for s in result.symbols if s.name == "add")
        assert add.start_line == 1
        assert add.end_line >= add.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "matlab")
        assert result.ok
        assert len(result.symbols) == 0

    def test_no_imports(self):
        result = self.parser.parse_source(SAMPLE_MATLAB, "matlab")
        assert len(result.imports) == 0

    def test_single_function(self):
        result = self.parser.parse_source("function hello()\n    disp('hi');\nend\n", "matlab")
        assert result.ok
        assert len(result.symbols) == 1
        assert result.symbols[0].name == "hello"

    def test_function_kind(self):
        result = self.parser.parse_source(SAMPLE_MATLAB, "matlab")
        assert all(s.kind == "function" for s in result.symbols)
