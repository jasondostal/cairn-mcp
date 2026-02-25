"""Tests for C# language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_CSHARP = '''
using System;
using System.Collections.Generic;

namespace MyApp {
    /// <summary>
    /// Direction enum
    /// </summary>
    enum Direction {
        North,
        South
    }

    /// <summary>
    /// A configurable interface
    /// </summary>
    interface IConfigurable {
        void Configure();
    }

    /// <summary>
    /// User class
    /// </summary>
    class User : IConfigurable {
        /// <summary>Name property</summary>
        public string Name { get; set; }

        private int _age;

        /// <summary>
        /// Configure the user
        /// </summary>
        public void Configure() {
            Console.WriteLine("configured");
        }

        public int GetAge() {
            return _age;
        }
    }
}
'''


class TestCSharpParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        assert result.ok
        assert result.language == "csharp"
        assert len(result.content_hash) == 64

    def test_namespace_extracted(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        ns = next(s for s in result.symbols if s.name == "MyApp")
        assert ns.kind == "namespace"

    def test_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        user = next(s for s in result.symbols if s.name == "User")
        assert user.kind == "class"

    def test_class_parent_is_namespace(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        user = next(s for s in result.symbols if s.name == "User")
        assert user.parent_name == "MyApp"

    def test_class_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        user = next(s for s in result.symbols if s.name == "User")
        assert user.qualified_name == "MyApp.User"

    def test_interface_extracted(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        iface = next(s for s in result.symbols if s.name == "IConfigurable")
        assert iface.kind == "interface"

    def test_enum_extracted(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        direction = next(s for s in result.symbols if s.name == "Direction")
        assert direction.kind == "enum"

    def test_method_extracted(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "Configure" in names
        assert "GetAge" in names

    def test_method_parent_name(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        get_age = next(s for s in result.symbols if s.name == "GetAge")
        assert get_age.parent_name == "User"
        assert get_age.kind == "method"

    def test_method_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        get_age = next(s for s in result.symbols if s.name == "GetAge")
        assert get_age.qualified_name == "User.GetAge"

    def test_property_extracted(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        name_prop = next(s for s in result.symbols if s.name == "Name")
        assert name_prop.kind == "property"
        assert name_prop.parent_name == "User"

    def test_field_extracted(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        age_field = next(s for s in result.symbols if s.name == "_age")
        assert age_field.kind == "field"
        assert age_field.parent_name == "User"

    def test_imports_extracted(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        assert len(result.imports) == 2
        import_names = {i.name for i in result.imports}
        assert "System" in import_names
        assert "System.Collections.Generic" in import_names

    def test_doc_comments(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        user = next(s for s in result.symbols if s.name == "User")
        assert user.docstring == "User class"

    def test_method_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        configure = next(
            s for s in result.symbols
            if s.name == "Configure" and s.parent_name == "User"
        )
        assert configure.docstring == "Configure the user"

    def test_enum_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        direction = next(s for s in result.symbols if s.name == "Direction")
        assert direction.docstring == "Direction enum"

    def test_property_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        name_prop = next(s for s in result.symbols if s.name == "Name")
        assert name_prop.docstring == "Name property"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        user = next(s for s in result.symbols if s.name == "User")
        assert user.start_line > 0
        assert user.end_line >= user.start_line

    def test_method_signature(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        get_age = next(s for s in result.symbols if s.name == "GetAge")
        assert "GetAge" in get_age.signature

    def test_empty_file(self):
        result = self.parser.parse_source("", "csharp")
        assert result.ok
        assert len(result.symbols) == 0

    def test_symbol_kinds(self):
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        kind_map = {s.name: s.kind for s in result.symbols}
        assert kind_map["MyApp"] == "namespace"
        assert kind_map["User"] == "class"
        assert kind_map["IConfigurable"] == "interface"
        assert kind_map["Direction"] == "enum"
        assert kind_map["GetAge"] == "method"
        assert kind_map["Name"] == "property"
        assert kind_map["_age"] == "field"

    def test_interface_method(self):
        """Interface methods should be extracted."""
        result = self.parser.parse_source(SAMPLE_CSHARP, "csharp")
        configure_methods = [s for s in result.symbols if s.name == "Configure"]
        assert len(configure_methods) >= 1
        parents = {s.parent_name for s in configure_methods}
        assert "IConfigurable" in parents
