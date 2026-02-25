"""Tests for Groovy language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_GROOVY = '''import groovy.json.JsonSlurper
import java.util.Map

class MyService {
    String name
    int count = 0

    void process(String data) {
        println data
    }

    static MyService create() {
        return new MyService()
    }
}
'''


class TestGroovyParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_GROOVY, "groovy")
        assert result.ok
        assert result.language == "groovy"
        assert len(result.content_hash) == 64

    def test_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_GROOVY, "groovy")
        classes = [s for s in result.symbols if s.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "MyService"

    def test_methods_extracted(self):
        result = self.parser.parse_source(SAMPLE_GROOVY, "groovy")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "process" in names
        assert "create" in names

    def test_fields_extracted(self):
        result = self.parser.parse_source(SAMPLE_GROOVY, "groovy")
        fields = [s for s in result.symbols if s.kind == "field"]
        names = {s.name for s in fields}
        assert "name" in names
        assert "count" in names

    def test_imports_extracted(self):
        result = self.parser.parse_source(SAMPLE_GROOVY, "groovy")
        imports = {s.name for s in result.imports}
        assert "groovy.json.JsonSlurper" in imports
        assert "java.util.Map" in imports

    def test_qualified_names(self):
        result = self.parser.parse_source(SAMPLE_GROOVY, "groovy")
        qnames = {s.qualified_name for s in result.symbols}
        assert "MyService" in qnames
        assert "MyService.process" in qnames

    def test_method_parent(self):
        result = self.parser.parse_source(SAMPLE_GROOVY, "groovy")
        method = next(s for s in result.symbols if s.name == "process")
        assert method.parent_name == "MyService"

    def test_method_signature(self):
        result = self.parser.parse_source(SAMPLE_GROOVY, "groovy")
        method = next(s for s in result.symbols if s.name == "process")
        assert "void" in method.signature
        assert "process" in method.signature

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_GROOVY, "groovy")
        cls = next(s for s in result.symbols if s.name == "MyService")
        assert cls.start_line > 0
        assert cls.end_line >= cls.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "groovy")
        assert result.ok
        assert len(result.symbols) == 0

    def test_import_signature(self):
        result = self.parser.parse_source(SAMPLE_GROOVY, "groovy")
        imp = next(s for s in result.imports if "JsonSlurper" in s.name)
        assert imp.signature == "import groovy.json.JsonSlurper"
