"""Tests for CSS language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_CSS = '''@import url("base.css");

:root {
  --primary: #333;
  --accent: blue;
}

body {
  margin: 0;
  padding: 0;
}

.container {
  max-width: 1200px;
  margin: 0 auto;
}

#header {
  background: var(--primary);
}

@media (max-width: 768px) {
  .container {
    padding: 10px;
  }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
'''


class TestCssParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_CSS, "css")
        assert result.ok
        assert result.language == "css"
        assert len(result.content_hash) == 64

    def test_selectors_extracted(self):
        result = self.parser.parse_source(SAMPLE_CSS, "css")
        names = {s.name for s in result.symbols if s.kind == "selector"}
        assert ":root" in names
        assert "body" in names
        assert ".container" in names
        assert "#header" in names

    def test_import_extracted(self):
        result = self.parser.parse_source(SAMPLE_CSS, "css")
        imports = {s.name for s in result.imports}
        assert "base.css" in imports

    def test_media_query(self):
        result = self.parser.parse_source(SAMPLE_CSS, "css")
        media = [s for s in result.symbols if s.kind == "media"]
        assert len(media) == 1
        assert "max-width" in media[0].signature

    def test_keyframes(self):
        result = self.parser.parse_source(SAMPLE_CSS, "css")
        kf = [s for s in result.symbols if s.kind == "keyframes"]
        assert len(kf) == 1
        assert kf[0].name == "fadeIn"

    def test_selector_kind(self):
        result = self.parser.parse_source(SAMPLE_CSS, "css")
        selectors = [s for s in result.symbols if s.kind == "selector"]
        assert len(selectors) == 4

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_CSS, "css")
        body = next(s for s in result.symbols if s.name == "body")
        assert body.start_line > 0
        assert body.end_line >= body.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "css")
        assert result.ok
        assert len(result.symbols) == 0

    def test_single_rule(self):
        result = self.parser.parse_source(".btn { color: blue; }", "css")
        assert result.ok
        assert len(result.symbols) == 1
        assert result.symbols[0].name == ".btn"

    def test_keyframes_signature(self):
        result = self.parser.parse_source(SAMPLE_CSS, "css")
        kf = next(s for s in result.symbols if s.kind == "keyframes")
        assert kf.signature == "@keyframes fadeIn"

    def test_no_docstring(self):
        result = self.parser.parse_source(SAMPLE_CSS, "css")
        assert all(s.docstring is None for s in result.symbols)
