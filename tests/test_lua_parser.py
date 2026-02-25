"""Tests for Lua language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_LUA = '''local json = require("json")
local utils = require("utils")

MAX_SIZE = 100
local count = 0

-- Greet a person by name
function greet(name)
  print("Hello, " .. name)
end

local function helper(x)
  return x * 2
end

local M = {}

function M.init(self)
  self.ready = true
end

function M:process(data)
  return data
end

return M
'''


class TestLuaParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        assert result.ok
        assert result.language == "lua"
        assert len(result.content_hash) == 64

    def test_global_function(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        names = {s.name for s in result.symbols if s.kind == "function"}
        assert "greet" in names

    def test_local_function(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        names = {s.name for s in result.symbols if s.kind == "function"}
        assert "helper" in names

    def test_method_dot(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "M.init" in names or any("init" in s.name for s in methods)

    def test_method_colon(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "M:process" in names or any("process" in s.name for s in methods)

    def test_require_imports(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        imports = {s.name for s in result.imports}
        assert "json" in imports
        assert "utils" in imports

    def test_global_variable(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        vars_ = [s for s in result.symbols if s.kind == "variable"]
        names = {s.name for s in vars_}
        assert "MAX_SIZE" in names

    def test_local_variable(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        vars_ = [s for s in result.symbols if s.kind == "variable"]
        names = {s.name for s in vars_}
        assert "count" in names

    def test_function_signature(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        greet = next(s for s in result.symbols if s.name == "greet")
        assert "function greet(name)" in greet.signature

    def test_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        greet = next(s for s in result.symbols if s.name == "greet")
        assert greet.docstring is not None
        assert "Greet" in greet.docstring

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_LUA, "lua")
        greet = next(s for s in result.symbols if s.name == "greet")
        assert greet.start_line > 0
        assert greet.end_line >= greet.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "lua")
        assert result.ok
        assert len(result.symbols) == 0

    def test_single_function(self):
        result = self.parser.parse_source("function hello() end\n", "lua")
        assert result.ok
        assert len(result.symbols) == 1
        assert result.symbols[0].name == "hello"
