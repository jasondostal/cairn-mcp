"""Tests for Zig language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_ZIG = '''const std = @import("std");
const mem = std.mem;

pub const MAX_SIZE: usize = 1024;

pub fn add(a: i32, b: i32) i32 {
    return a + b;
}

fn helper() void {}

const Point = struct {
    x: f64,
    y: f64,

    pub fn distance(self: Point) f64 {
        return std.math.sqrt(self.x * self.x + self.y * self.y);
    }
};

const Color = enum { red, green, blue };

test "add test" {
    try std.testing.expectEqual(add(1, 2), 3);
}
'''


class TestZigParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        assert result.ok
        assert result.language == "zig"
        assert len(result.content_hash) == 64

    def test_import_extracted(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        imports = {s.name for s in result.imports}
        assert "std" in imports

    def test_functions_extracted(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        funcs = [s for s in result.symbols if s.kind == "function"]
        names = {s.name for s in funcs}
        assert "add" in names
        assert "helper" in names

    def test_struct_extracted(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        structs = [s for s in result.symbols if s.kind == "struct"]
        assert len(structs) == 1
        assert structs[0].name == "Point"

    def test_struct_method(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "distance" in names

    def test_method_parent(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        method = next(s for s in result.symbols if s.name == "distance")
        assert method.parent_name == "Point"

    def test_enum_extracted(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        enums = [s for s in result.symbols if s.kind == "enum"]
        assert len(enums) == 1
        assert enums[0].name == "Color"

    def test_constant_extracted(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        consts = [s for s in result.symbols if s.kind == "constant"]
        names = {s.name for s in consts}
        assert "MAX_SIZE" in names
        assert "mem" in names

    def test_test_declaration(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        tests = [s for s in result.symbols if s.kind == "test"]
        assert len(tests) == 1
        assert "add" in tests[0].name

    def test_function_signature(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        add = next(s for s in result.symbols if s.name == "add")
        assert "pub fn add" in add.signature
        assert "i32" in add.signature

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        add = next(s for s in result.symbols if s.name == "add")
        assert add.start_line > 0
        assert add.end_line >= add.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "zig")
        assert result.ok
        assert len(result.symbols) == 0

    def test_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_ZIG, "zig")
        method = next(s for s in result.symbols if s.name == "distance")
        assert method.qualified_name == "Point.distance"
