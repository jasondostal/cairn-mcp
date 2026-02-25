"""Tests for Kotlin language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_KOTLIN = '''
import kotlin.collections.List
import kotlin.io.println

/**
 * A configurable interface
 */
interface Configurable {
    fun configure()
}

/**
 * A point data class
 */
data class Point(val x: Double, val y: Double)

/**
 * Main application object
 */
object App {
    val version: String = "1.0"

    /** Entry point */
    fun main(args: Array<String>) {
        println("hello")
    }
}

/**
 * User class
 */
class User(val name: String) : Configurable {
    val active: Boolean = true

    /** Configure the user */
    override fun configure() {}
}

/** Top level greet function */
fun greet(name: String): String {
    return "Hello"
}

val globalVal: Int = 42
'''


class TestKotlinParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        assert result.ok
        assert result.language == "kotlin"
        assert len(result.content_hash) == 64

    def test_interface_extracted(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        configurable = next(s for s in result.symbols if s.name == "Configurable")
        assert configurable.kind == "interface"

    def test_data_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        point = next(s for s in result.symbols if s.name == "Point")
        assert point.kind == "data_class"

    def test_object_extracted(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        app = next(s for s in result.symbols if s.name == "App")
        assert app.kind == "object"

    def test_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        user = next(s for s in result.symbols if s.name == "User")
        assert user.kind == "class"

    def test_function_extracted(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        greet = next(s for s in result.symbols if s.name == "greet")
        assert greet.kind == "function"

    def test_method_extracted(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "main" in names
        assert "configure" in names

    def test_method_parent_name(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        main = next(s for s in result.symbols if s.name == "main")
        assert main.parent_name == "App"
        assert main.kind == "method"

    def test_method_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        main = next(s for s in result.symbols if s.name == "main")
        assert main.qualified_name == "App.main"

    def test_property_extracted(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        props = [s for s in result.symbols if s.kind == "property"]
        names = {s.name for s in props}
        assert "version" in names
        assert "active" in names
        assert "globalVal" in names

    def test_property_parent(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        version = next(s for s in result.symbols if s.name == "version")
        assert version.parent_name == "App"
        assert version.qualified_name == "App.version"

    def test_imports_extracted(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        assert len(result.imports) == 2
        import_names = {i.name for i in result.imports}
        assert "kotlin.collections.List" in import_names
        assert "kotlin.io.println" in import_names

    def test_doc_comments(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        app = next(s for s in result.symbols if s.name == "App")
        assert app.docstring == "Main application object"

    def test_method_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        main = next(s for s in result.symbols if s.name == "main")
        assert main.docstring == "Entry point"

    def test_interface_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        configurable = next(s for s in result.symbols if s.name == "Configurable")
        assert configurable.docstring == "A configurable interface"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        app = next(s for s in result.symbols if s.name == "App")
        assert app.start_line > 0
        assert app.end_line >= app.start_line

    def test_function_signature(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        greet = next(s for s in result.symbols if s.name == "greet")
        assert "fun greet" in greet.signature
        assert "String" in greet.signature

    def test_empty_file(self):
        result = self.parser.parse_source("", "kotlin")
        assert result.ok
        assert len(result.symbols) == 0

    def test_symbol_kinds(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        kind_map = {s.name: s.kind for s in result.symbols}
        assert kind_map["Configurable"] == "interface"
        assert kind_map["Point"] == "data_class"
        assert kind_map["App"] == "object"
        assert kind_map["User"] == "class"
        assert kind_map["greet"] == "function"
        assert kind_map["main"] == "method"

    def test_interface_method(self):
        """Interface method declarations should be extracted."""
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        configure_methods = [s for s in result.symbols if s.name == "configure"]
        assert len(configure_methods) >= 1
        parents = {s.parent_name for s in configure_methods}
        assert "Configurable" in parents

    def test_global_property(self):
        result = self.parser.parse_source(SAMPLE_KOTLIN, "kotlin")
        gv = next(s for s in result.symbols if s.name == "globalVal")
        assert gv.kind == "property"
        assert gv.parent_name is None
        assert gv.qualified_name == "globalVal"
