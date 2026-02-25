"""Tests for Ruby language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_RUBY = '''
require "json"
require_relative "./helpers"

# Maximum retries.
MAX_RETRIES = 3

# Application configuration.
class Config
  attr_reader :host

  # Create a new config.
  def initialize(host)
    @host = host
  end

  def address
    host
  end
end

module Helpers
  # Format a value.
  def self.format(val)
    val.to_s
  end
end

def standalone(x)
  x > 0
end
'''


class TestRubyParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        assert result.ok
        assert result.language == "ruby"

    def test_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.kind == "class"

    def test_module_extracted(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        helpers = next(s for s in result.symbols if s.name == "Helpers")
        assert helpers.kind == "module"

    def test_instance_methods(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        init = next(s for s in result.symbols if s.name == "initialize")
        assert init.kind == "method"
        assert init.parent_name == "Config"

    def test_method_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        addr = next(s for s in result.symbols if s.name == "address")
        assert addr.qualified_name == "Config.address"

    def test_singleton_method(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        fmt = next(s for s in result.symbols if s.name == "format")
        assert fmt.kind == "method"
        assert fmt.parent_name == "Helpers"
        assert "self." in fmt.signature

    def test_standalone_function(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        f = next(s for s in result.symbols if s.name == "standalone")
        assert f.kind == "function"
        assert f.parent_name is None

    def test_constant(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        c = next(s for s in result.symbols if s.name == "MAX_RETRIES")
        assert c.kind == "constant"

    def test_require_as_imports(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        assert len(result.imports) == 2
        import_texts = {i.name for i in result.imports}
        assert any("json" in t for t in import_texts)
        assert any("helpers" in t for t in import_texts)

    def test_doc_comments(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.docstring == "Application configuration."
        init = next(s for s in result.symbols if s.name == "initialize")
        assert init.docstring == "Create a new config."

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_RUBY, "ruby")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.start_line > 0
        assert config.end_line >= config.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "ruby")
        assert result.ok
        assert len(result.symbols) == 0

    def test_class_with_superclass(self):
        source = '''
class MyList < Array
  def size
    super
  end
end
'''
        result = self.parser.parse_source(source, "ruby")
        my_list = next(s for s in result.symbols if s.name == "MyList")
        assert "< Array" in my_list.signature
