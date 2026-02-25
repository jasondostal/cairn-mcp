"""Tests for Scala language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_SCALA = '''
import scala.collection.mutable
import scala.io.Source

/** A configuration trait */
trait Configurable {
  def configure(): Unit
}

/** Main application object */
object App {
  /** Entry point */
  def main(args: Array[String]): Unit = {
    println("hello")
  }
  val version: String = "1.0"
}

/** User class */
class User(val name: String, val age: Int) extends Configurable {
  /** Configure the user */
  def configure(): Unit = {}
  val active: Boolean = true
}

/** A point case class */
case class Point(x: Double, y: Double)
'''


class TestScalaParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        assert result.ok
        assert result.language == "scala"
        assert len(result.content_hash) == 64

    def test_trait_extracted(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        configurable = next(s for s in result.symbols if s.name == "Configurable")
        assert configurable.kind == "trait"

    def test_object_extracted(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        app = next(s for s in result.symbols if s.name == "App")
        assert app.kind == "object"

    def test_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        user = next(s for s in result.symbols if s.name == "User")
        assert user.kind == "class"

    def test_case_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        point = next(s for s in result.symbols if s.name == "Point")
        assert point.kind == "case_class"

    def test_method_extracted(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "main" in names
        assert "configure" in names

    def test_method_parent_name(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        main = next(s for s in result.symbols if s.name == "main")
        assert main.parent_name == "App"
        assert main.kind == "method"

    def test_method_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        main = next(s for s in result.symbols if s.name == "main")
        assert main.qualified_name == "App.main"

    def test_val_extracted(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        vals = [s for s in result.symbols if s.kind == "val"]
        names = {s.name for s in vals}
        assert "version" in names
        assert "active" in names

    def test_val_parent(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        version = next(s for s in result.symbols if s.name == "version")
        assert version.parent_name == "App"
        assert version.qualified_name == "App.version"

    def test_imports_extracted(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        assert len(result.imports) == 2
        import_names = {i.name for i in result.imports}
        assert "scala.collection.mutable" in import_names
        assert "scala.io.Source" in import_names

    def test_doc_comments(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        app = next(s for s in result.symbols if s.name == "App")
        assert app.docstring == "Main application object"

    def test_method_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        main = next(s for s in result.symbols if s.name == "main")
        assert main.docstring == "Entry point"

    def test_trait_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        configurable = next(s for s in result.symbols if s.name == "Configurable")
        assert configurable.docstring == "A configuration trait"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        app = next(s for s in result.symbols if s.name == "App")
        assert app.start_line > 0
        assert app.end_line >= app.start_line

    def test_function_signature(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        main = next(s for s in result.symbols if s.name == "main")
        assert "def main" in main.signature

    def test_empty_file(self):
        result = self.parser.parse_source("", "scala")
        assert result.ok
        assert len(result.symbols) == 0

    def test_symbol_kinds(self):
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        kind_map = {s.name: s.kind for s in result.symbols}
        assert kind_map["Configurable"] == "trait"
        assert kind_map["App"] == "object"
        assert kind_map["User"] == "class"
        assert kind_map["Point"] == "case_class"
        assert kind_map["main"] == "method"

    def test_trait_method_as_declaration(self):
        """Trait abstract methods (function_declaration) should be extracted."""
        result = self.parser.parse_source(SAMPLE_SCALA, "scala")
        # configure appears in both trait and class
        configure_methods = [s for s in result.symbols if s.name == "configure"]
        assert len(configure_methods) >= 1
        parents = {s.parent_name for s in configure_methods}
        assert "Configurable" in parents
