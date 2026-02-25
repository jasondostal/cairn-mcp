"""Tests for the tree-sitter code parser."""

from pathlib import Path

from cairn.code.parser import CodeParser, CodeSymbol, ParseResult


SAMPLE_PYTHON = '''
import os
from pathlib import Path

CONSTANT = 42
MAX_SIZE = 100

class MyClass:
    """A sample class."""

    def method(self, x: int) -> str:
        """Convert x to string."""
        return str(x)

    def _private(self):
        pass

def standalone(a, b):
    """Add two numbers."""
    return a + b

variable = "not a constant"
'''


class TestCodeParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        assert result.ok
        assert result.language == "python"
        assert len(result.content_hash) == 64  # SHA-256

    def test_symbols_extracted(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        names = {s.name for s in result.symbols}
        assert "MyClass" in names
        assert "method" in names
        assert "_private" in names
        assert "standalone" in names
        assert "CONSTANT" in names
        assert "MAX_SIZE" in names

    def test_imports_extracted(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        assert len(result.imports) == 2
        import_texts = {i.name for i in result.imports}
        assert "import os" in import_texts
        assert "from pathlib import Path" in import_texts

    def test_symbol_kinds(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        kind_map = {s.name: s.kind for s in result.symbols}
        assert kind_map["MyClass"] == "class"
        assert kind_map["method"] == "method"
        assert kind_map["standalone"] == "function"
        assert kind_map["CONSTANT"] == "constant"

    def test_qualified_names(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        qnames = {s.qualified_name for s in result.symbols}
        assert "MyClass" in qnames
        assert "MyClass.method" in qnames
        assert "MyClass._private" in qnames
        assert "standalone" in qnames

    def test_method_parent(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        method = next(s for s in result.symbols if s.name == "method")
        assert method.parent_name == "MyClass"

    def test_function_no_parent(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        func = next(s for s in result.symbols if s.name == "standalone")
        assert func.parent_name is None

    def test_docstrings(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        cls = next(s for s in result.symbols if s.name == "MyClass")
        assert cls.docstring == "A sample class."
        method = next(s for s in result.symbols if s.name == "method")
        assert method.docstring == "Convert x to string."
        func = next(s for s in result.symbols if s.name == "standalone")
        assert func.docstring == "Add two numbers."

    def test_signatures(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        method = next(s for s in result.symbols if s.name == "method")
        assert "def method(self, x: int)" in method.signature
        cls = next(s for s in result.symbols if s.name == "MyClass")
        assert cls.signature == "class MyClass"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        cls = next(s for s in result.symbols if s.name == "MyClass")
        assert cls.start_line > 0
        assert cls.end_line >= cls.start_line

    def test_content_hash_deterministic(self):
        r1 = self.parser.parse_source("x = 1", "python")
        r2 = self.parser.parse_source("x = 1", "python")
        assert r1.content_hash == r2.content_hash

    def test_content_hash_changes(self):
        r1 = self.parser.parse_source("x = 1", "python")
        r2 = self.parser.parse_source("x = 2", "python")
        assert r1.content_hash != r2.content_hash

    def test_syntax_error_still_parses(self):
        # tree-sitter is error-tolerant
        result = self.parser.parse_source("def broken(\n", "python")
        assert result.ok  # tree-sitter doesn't fail on syntax errors

    def test_empty_file(self):
        result = self.parser.parse_source("", "python")
        assert result.ok
        assert len(result.symbols) == 0

    def test_unsupported_extension(self):
        result = self.parser.parse_file(Path("test.xyz"))
        assert result is None

    def test_nonexistent_file(self):
        result = self.parser.parse_file(Path("/nonexistent/file.py"))
        assert result is not None
        assert not result.ok

    def test_all_symbols_includes_imports(self):
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        all_syms = result.all_symbols
        assert len(all_syms) == len(result.symbols) + len(result.imports)

    def test_lowercase_not_constant(self):
        """Non-ALL_CAPS assignments should not be extracted as constants."""
        result = self.parser.parse_source(SAMPLE_PYTHON, "python")
        names = {s.name for s in result.symbols}
        assert "variable" not in names


class TestParseDirectory:

    def test_parse_cairn_codebase(self):
        """Parse the actual cairn codebase — smoke test."""
        parser = CodeParser()
        results = parser.parse_directory(Path("cairn"))
        assert len(results) > 50  # We know there are 100+ files
        errors = [r for r in results if not r.ok]
        assert len(errors) == 0
        total_symbols = sum(len(r.symbols) for r in results)
        assert total_symbols > 500  # We know there are 1000+


class TestDecorators:

    def test_decorated_function(self):
        source = '''
@decorator
def my_func():
    """Decorated."""
    pass
'''
        parser = CodeParser()
        result = parser.parse_source(source, "python")
        assert any(s.name == "my_func" for s in result.symbols)
        func = next(s for s in result.symbols if s.name == "my_func")
        assert func.kind == "function"
        assert func.docstring == "Decorated."

    def test_decorated_class(self):
        source = '''
@dataclass
class Config:
    """Config class."""
    name: str = "default"
'''
        parser = CodeParser()
        result = parser.parse_source(source, "python")
        assert any(s.name == "Config" for s in result.symbols)
        cls = next(s for s in result.symbols if s.name == "Config")
        assert cls.kind == "class"
