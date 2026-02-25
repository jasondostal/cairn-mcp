"""Tests for OCaml language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_OCAML = '''open Printf

let greeting = "hello"

let add x y = x + y

let rec factorial n =
  if n <= 1 then 1
  else n * factorial (n - 1)

type point = { x: float; y: float }

type color = Red | Green | Blue

module MyModule = struct
  let helper x = x * 2
  type t = int
end
'''


class TestOcamlParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        assert result.ok
        assert result.language == "ocaml"
        assert len(result.content_hash) == 64

    def test_open_extracted(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        imports = {s.name for s in result.imports}
        assert "Printf" in imports

    def test_value_binding(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        vars_ = [s for s in result.symbols if s.kind == "variable"]
        names = {s.name for s in vars_}
        assert "greeting" in names

    def test_function_extracted(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        funcs = [s for s in result.symbols if s.kind == "function"]
        names = {s.name for s in funcs}
        assert "add" in names
        assert "factorial" in names

    def test_type_definitions(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        types = [s for s in result.symbols if s.kind == "type"]
        names = {s.name for s in types}
        assert "point" in names
        assert "color" in names

    def test_module_extracted(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        modules = [s for s in result.symbols if s.kind == "module"]
        assert len(modules) == 1
        assert modules[0].name == "MyModule"

    def test_module_member(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        helper = next((s for s in result.symbols if s.name == "helper"), None)
        assert helper is not None
        assert helper.parent_name == "MyModule"
        assert helper.qualified_name == "MyModule.helper"

    def test_module_type(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        types = [s for s in result.symbols if s.kind == "type"]
        names = {s.name for s in types}
        assert "t" in names

    def test_function_signature(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        add = next(s for s in result.symbols if s.name == "add")
        assert "let add x y" in add.signature

    def test_rec_function_signature(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        fact = next(s for s in result.symbols if s.name == "factorial")
        assert "let rec factorial" in fact.signature

    def test_open_signature(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        imp = next(s for s in result.imports)
        assert imp.signature == "open Printf"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_OCAML, "ocaml")
        add = next(s for s in result.symbols if s.name == "add")
        assert add.start_line > 0
        assert add.end_line >= add.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "ocaml")
        assert result.ok
        assert len(result.symbols) == 0

    def test_single_let(self):
        result = self.parser.parse_source("let x = 42\n", "ocaml")
        assert result.ok
        assert len(result.symbols) == 1
        assert result.symbols[0].name == "x"
