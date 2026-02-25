"""Tests for Java language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_JAVA = '''
package com.example;

import java.util.List;
import java.util.Map;

/**
 * Application configuration.
 */
public class Config {
    private static final int MAX_RETRIES = 3;

    private String host;

    /**
     * Create a new config.
     */
    public Config(String host) {
        this.host = host;
    }

    /**
     * Get the host.
     */
    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }
}

/**
 * A handler interface.
 */
public interface Handler {
    void handle(Request req);
}

public enum Status {
    ACTIVE,
    INACTIVE
}

public record Point(int x, int y) {}
'''


class TestJavaParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        assert result.ok
        assert result.language == "java"
        assert len(result.content_hash) == 64

    def test_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.kind == "class"
        assert "public" in config.signature

    def test_interface_extracted(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        handler = next(s for s in result.symbols if s.name == "Handler")
        assert handler.kind == "interface"

    def test_enum_extracted(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        status = next(s for s in result.symbols if s.name == "Status")
        assert status.kind == "enum"

    def test_record_extracted(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        point = next(s for s in result.symbols if s.name == "Point")
        assert point.kind == "record"
        assert "(int x, int y)" in point.signature

    def test_constructor_extracted(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        ctor = next(s for s in result.symbols if s.name == "Config" and s.kind == "constructor")
        assert ctor.parent_name == "Config"
        assert ctor.qualified_name == "Config.Config"

    def test_methods_extracted(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "getHost" in names
        assert "setHost" in names
        assert "handle" in names

    def test_method_parent(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        get_host = next(s for s in result.symbols if s.name == "getHost")
        assert get_host.parent_name == "Config"
        assert get_host.qualified_name == "Config.getHost"

    def test_static_final_constant(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        c = next(s for s in result.symbols if s.name == "MAX_RETRIES")
        assert c.kind == "constant"
        assert c.parent_name == "Config"

    def test_imports_extracted(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        assert len(result.imports) == 2
        import_texts = {i.name for i in result.imports}
        assert any("java.util.List" in t for t in import_texts)
        assert any("java.util.Map" in t for t in import_texts)

    def test_javadoc(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        config = next(s for s in result.symbols if s.name == "Config" and s.kind == "class")
        assert config.docstring == "Application configuration."
        get_host = next(s for s in result.symbols if s.name == "getHost")
        assert get_host.docstring == "Get the host."

    def test_method_signatures(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        get_host = next(s for s in result.symbols if s.name == "getHost")
        assert "String" in get_host.signature
        assert "getHost()" in get_host.signature

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        config = next(s for s in result.symbols if s.name == "Config" and s.kind == "class")
        assert config.start_line > 0
        assert config.end_line >= config.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "java")
        assert result.ok
        assert len(result.symbols) == 0

    def test_interface_method(self):
        result = self.parser.parse_source(SAMPLE_JAVA, "java")
        handle = next(s for s in result.symbols if s.name == "handle")
        assert handle.parent_name == "Handler"

    def test_nested_class(self):
        source = '''
public class Outer {
    public class Inner {
        public void doThing() {}
    }
}
'''
        result = self.parser.parse_source(source, "java")
        inner = next(s for s in result.symbols if s.name == "Inner")
        assert inner.parent_name == "Outer"
        assert inner.qualified_name == "Outer.Inner"
        do_thing = next(s for s in result.symbols if s.name == "doThing")
        assert do_thing.parent_name == "Inner"

    def test_extends_implements(self):
        source = '''
public class MyList extends ArrayList implements Serializable {
}
'''
        result = self.parser.parse_source(source, "java")
        my_list = next(s for s in result.symbols if s.name == "MyList")
        assert "extends" in my_list.signature
        assert "implements" in my_list.signature
