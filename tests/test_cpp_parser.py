"""Tests for C++ language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_CPP = '''
#include <string>
#include <vector>

namespace myns {

/** A config class. */
class Config {
public:
    Config(std::string host, int port);
    std::string address() const;
private:
    std::string host_;
    int port_;
};

Config::Config(std::string host, int port) : host_(host), port_(port) {}

std::string Config::address() const {
    return host_ + ":" + std::to_string(port_);
}

template<typename T>
T identity(T val) { return val; }

struct Point {
    int x;
    int y;
};

enum class Color { Red, Green, Blue };

} // namespace myns
'''


class TestCppParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        assert result.ok
        assert result.language == "cpp"

    def test_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        config = next(s for s in result.symbols if s.name == "Config" and s.kind == "class")
        assert config.kind == "class"

    def test_namespace_extracted(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        ns = next(s for s in result.symbols if s.name == "myns")
        assert ns.kind == "namespace"

    def test_struct_extracted(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        point = next(s for s in result.symbols if s.name == "Point")
        assert point.kind == "struct"

    def test_enum_class(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        color = next(s for s in result.symbols if s.name == "Color")
        assert color.kind == "enum"
        assert "enum class" in color.signature

    def test_out_of_line_method(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        addr = next(s for s in result.symbols if s.name == "address")
        assert addr.kind == "method"
        assert addr.parent_name == "Config"
        assert addr.qualified_name == "Config.address"

    def test_out_of_line_constructor(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        ctors = [s for s in result.symbols if s.name == "Config" and s.kind == "method"]
        assert len(ctors) >= 1

    def test_template_function(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        identity = next(s for s in result.symbols if s.name == "identity")
        assert identity.kind in ("function", "method")

    def test_includes_as_imports(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        assert len(result.imports) == 2

    def test_class_method_declarations(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        # Inline declarations inside class body
        methods = [s for s in result.symbols if s.parent_name == "Config" and s.kind == "method"]
        names = {s.name for s in methods}
        assert "address" in names

    def test_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        config = next(s for s in result.symbols if s.name == "Config" and s.kind == "class")
        assert config.docstring == "A config class."

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        config = next(s for s in result.symbols if s.name == "Config" and s.kind == "class")
        assert config.start_line > 0
        assert config.end_line >= config.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "cpp")
        assert result.ok
        assert len(result.symbols) == 0

    def test_nested_in_namespace(self):
        result = self.parser.parse_source(SAMPLE_CPP, "cpp")
        config = next(s for s in result.symbols if s.name == "Config" and s.kind == "class")
        assert config.parent_name == "myns"
