"""Tests for Swift language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_SWIFT = '''
import Foundation
import UIKit

/// A configuration class
class Config {
    /// The host name
    var host: String = "localhost"
    let port: Int = 8080

    /// Start the config
    func start() -> Bool {
        return true
    }
}

/// A point struct
struct Point {
    var x: Double
    var y: Double

    /// Calculate distance
    func distance() -> Double {
        return 0.0
    }
}

/// A readable protocol
protocol Readable {
    func read() -> String
}

/// Direction enum
enum Direction {
    case north
    case south
}

/// Top level greet function
func greet(name: String) -> String {
    return "Hello"
}
'''


class TestSwiftParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        assert result.ok
        assert result.language == "swift"
        assert len(result.content_hash) == 64

    def test_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.kind == "class"

    def test_struct_extracted(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        point = next(s for s in result.symbols if s.name == "Point")
        assert point.kind == "struct"

    def test_protocol_extracted(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        readable = next(s for s in result.symbols if s.name == "Readable")
        assert readable.kind == "protocol"

    def test_enum_extracted(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        direction = next(s for s in result.symbols if s.name == "Direction")
        assert direction.kind == "enum"

    def test_function_extracted(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        greet = next(s for s in result.symbols if s.name == "greet")
        assert greet.kind == "function"

    def test_method_extracted(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "start" in names
        assert "distance" in names

    def test_method_parent_name(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        start = next(s for s in result.symbols if s.name == "start")
        assert start.parent_name == "Config"
        assert start.kind == "method"

    def test_method_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        start = next(s for s in result.symbols if s.name == "start")
        assert start.qualified_name == "Config.start"

    def test_property_extracted(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        props = [s for s in result.symbols if s.kind == "property"]
        names = {s.name for s in props}
        assert "host" in names
        assert "port" in names

    def test_property_parent(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        host = next(s for s in result.symbols if s.name == "host")
        assert host.parent_name == "Config"
        assert host.qualified_name == "Config.host"

    def test_imports_extracted(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        assert len(result.imports) == 2
        import_names = {i.name for i in result.imports}
        assert "Foundation" in import_names
        assert "UIKit" in import_names

    def test_doc_comments(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.docstring == "A configuration class"

    def test_method_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        start = next(s for s in result.symbols if s.name == "start")
        assert start.docstring == "Start the config"

    def test_property_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        host = next(s for s in result.symbols if s.name == "host")
        assert host.docstring == "The host name"

    def test_protocol_method_extracted(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        read = next(s for s in result.symbols if s.name == "read")
        assert read.kind == "method"
        assert read.parent_name == "Readable"
        assert read.qualified_name == "Readable.read"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.start_line > 0
        assert config.end_line >= config.start_line

    def test_function_signature(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        greet = next(s for s in result.symbols if s.name == "greet")
        assert "func greet" in greet.signature
        assert "String" in greet.signature

    def test_empty_file(self):
        result = self.parser.parse_source("", "swift")
        assert result.ok
        assert len(result.symbols) == 0

    def test_block_doc_comment(self):
        source = '''
/**
 * A block documented function
 */
func documented() {}
'''
        result = self.parser.parse_source(source, "swift")
        func = next(s for s in result.symbols if s.name == "documented")
        assert "block documented function" in func.docstring

    def test_symbol_kinds(self):
        result = self.parser.parse_source(SAMPLE_SWIFT, "swift")
        kind_map = {s.name: s.kind for s in result.symbols}
        assert kind_map["Config"] == "class"
        assert kind_map["Point"] == "struct"
        assert kind_map["Readable"] == "protocol"
        assert kind_map["Direction"] == "enum"
        assert kind_map["greet"] == "function"
        assert kind_map["start"] == "method"
