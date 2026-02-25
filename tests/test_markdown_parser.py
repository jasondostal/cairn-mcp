"""Tests for Markdown language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_MARKDOWN = '''# Main Title

Some introductory paragraph text here.

## Getting Started

Follow these steps to begin.

### Prerequisites

- Python 3.11+
- PostgreSQL 15+

### Installation

```bash
pip install cairn-mcp
```

## Configuration

Set up your environment variables.

### Database Setup

Create the database and run migrations.

## API Reference

Detailed API documentation below.
'''


class TestMarkdownParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        assert result.ok
        assert result.language == "markdown"
        assert len(result.content_hash) == 64

    def test_headings_extracted(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        names = {s.name for s in result.symbols}
        assert "Main Title" in names
        assert "Getting Started" in names
        assert "Prerequisites" in names
        assert "Installation" in names
        assert "Configuration" in names
        assert "Database Setup" in names
        assert "API Reference" in names

    def test_heading_count(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        assert len(result.symbols) == 7

    def test_heading_kind(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        assert all(s.kind == "heading" for s in result.symbols)

    def test_h1_signature(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        h1 = next(s for s in result.symbols if s.name == "Main Title")
        assert h1.signature == "# Main Title"

    def test_h2_signature(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        h2 = next(s for s in result.symbols if s.name == "Getting Started")
        assert h2.signature == "## Getting Started"

    def test_h3_signature(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        h3 = next(s for s in result.symbols if s.name == "Prerequisites")
        assert h3.signature == "### Prerequisites"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        h1 = next(s for s in result.symbols if s.name == "Main Title")
        assert h1.start_line == 1
        assert h1.end_line >= h1.start_line

    def test_line_numbers_later_heading(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        config = next(s for s in result.symbols if s.name == "Configuration")
        assert config.start_line > 1

    def test_docstring_is_none(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        assert all(s.docstring is None for s in result.symbols)

    def test_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        h1 = next(s for s in result.symbols if s.name == "Main Title")
        assert h1.qualified_name == "Main Title"

    def test_no_imports(self):
        result = self.parser.parse_source(SAMPLE_MARKDOWN, "markdown")
        assert len(result.imports) == 0

    def test_empty_file(self):
        result = self.parser.parse_source("", "markdown")
        assert result.ok
        assert len(result.symbols) == 0

    def test_single_heading(self):
        result = self.parser.parse_source("# Hello\n", "markdown")
        assert result.ok
        assert len(result.symbols) == 1
        assert result.symbols[0].name == "Hello"
        assert result.symbols[0].signature == "# Hello"

    def test_no_headings(self):
        result = self.parser.parse_source("Just a paragraph.\n", "markdown")
        assert result.ok
        assert len(result.symbols) == 0
