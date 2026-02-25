"""Tests for C language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_C = '''
#include <stdio.h>
#include "myheader.h"

#define MAX_SIZE 100

/** A config struct. */
typedef struct {
    char *host;
    int port;
} Config;

/** Create a config. */
Config* config_new(const char *host, int port) {
    return NULL;
}

static void helper(void) {}

int main(int argc, char **argv) {
    return 0;
}
'''


class TestCParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_C, "c")
        assert result.ok
        assert result.language == "c"

    def test_functions_extracted(self):
        result = self.parser.parse_source(SAMPLE_C, "c")
        names = {s.name for s in result.symbols}
        assert "config_new" in names
        assert "helper" in names
        assert "main" in names

    def test_typedef_struct(self):
        result = self.parser.parse_source(SAMPLE_C, "c")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.kind == "struct"

    def test_define_constant(self):
        result = self.parser.parse_source(SAMPLE_C, "c")
        c = next(s for s in result.symbols if s.name == "MAX_SIZE")
        assert c.kind == "constant"

    def test_includes_as_imports(self):
        result = self.parser.parse_source(SAMPLE_C, "c")
        assert len(result.imports) == 2
        import_texts = {i.name for i in result.imports}
        assert any("stdio.h" in t for t in import_texts)
        assert any("myheader.h" in t for t in import_texts)

    def test_function_signature(self):
        result = self.parser.parse_source(SAMPLE_C, "c")
        main = next(s for s in result.symbols if s.name == "main")
        assert "int" in main.signature
        assert "main" in main.signature

    def test_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_C, "c")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.docstring == "A config struct."

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_C, "c")
        main = next(s for s in result.symbols if s.name == "main")
        assert main.start_line > 0
        assert main.end_line >= main.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "c")
        assert result.ok
        assert len(result.symbols) == 0

    def test_named_struct(self):
        source = '''
struct Point {
    int x;
    int y;
};
'''
        result = self.parser.parse_source(source, "c")
        point = next(s for s in result.symbols if s.name == "Point")
        assert point.kind == "struct"

    def test_enum(self):
        source = '''
typedef enum {
    RED,
    GREEN,
    BLUE
} Color;
'''
        result = self.parser.parse_source(source, "c")
        color = next(s for s in result.symbols if s.name == "Color")
        assert color.kind == "enum"
