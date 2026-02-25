"""Tests for HTML language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_HTML = '''<html lang="en">
<head>
  <title>Test Page</title>
  <link rel="stylesheet" href="style.css">
  <link rel="icon" href="favicon.ico">
  <script src="vendor.js"></script>
</head>
<body id="main" class="container">
  <div id="app">
    <h1>Hello World</h1>
    <img src="logo.png" alt="Logo" />
  </div>
  <script src="app.js"></script>
</body>
</html>
'''


class TestHtmlParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_HTML, "html")
        assert result.ok
        assert result.language == "html"
        assert len(result.content_hash) == 64

    def test_elements_with_id(self):
        result = self.parser.parse_source(SAMPLE_HTML, "html")
        names = {s.name for s in result.symbols if s.kind == "element"}
        assert "main" in names
        assert "app" in names

    def test_script_imports(self):
        result = self.parser.parse_source(SAMPLE_HTML, "html")
        imports = {s.name for s in result.imports}
        assert "app.js" in imports
        assert "vendor.js" in imports

    def test_link_imports(self):
        result = self.parser.parse_source(SAMPLE_HTML, "html")
        imports = {s.name for s in result.imports}
        assert "style.css" in imports

    def test_img_imports(self):
        result = self.parser.parse_source(SAMPLE_HTML, "html")
        imports = {s.name for s in result.imports}
        assert "logo.png" in imports

    def test_element_kind(self):
        result = self.parser.parse_source(SAMPLE_HTML, "html")
        id_syms = [s for s in result.symbols if s.kind == "element"]
        assert len(id_syms) >= 2

    def test_import_kind(self):
        result = self.parser.parse_source(SAMPLE_HTML, "html")
        assert all(s.kind == "import" for s in result.imports)

    def test_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_HTML, "html")
        main = next(s for s in result.symbols if s.name == "main")
        assert main.qualified_name == "body#main"

    def test_signature(self):
        result = self.parser.parse_source(SAMPLE_HTML, "html")
        main = next(s for s in result.symbols if s.name == "main")
        assert 'id="main"' in main.signature

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_HTML, "html")
        main = next(s for s in result.symbols if s.name == "main")
        assert main.start_line > 0
        assert main.end_line >= main.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "html")
        assert result.ok
        assert len(result.symbols) == 0

    def test_no_id_elements(self):
        result = self.parser.parse_source("<html><body><p>Text</p></body></html>", "html")
        assert result.ok
        assert len(result.symbols) == 0

    def test_self_closing_tag(self):
        result = self.parser.parse_source('<div id="root"><br/></div>', "html")
        assert result.ok
        names = {s.name for s in result.symbols if s.kind == "element"}
        assert "root" in names

    def test_script_without_src(self):
        result = self.parser.parse_source('<script>console.log("hello")</script>', "html")
        assert result.ok
        assert len(result.imports) == 0
