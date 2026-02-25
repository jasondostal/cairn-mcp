"""Tests for Rust language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_RUST = '''
use std::collections::HashMap;
use std::io::{self, Read};

/// Maximum number of retries.
const MAX_RETRIES: u32 = 3;

static DEFAULT_HOST: &str = "localhost";

/// Application configuration.
pub struct Config {
    host: String,
    port: u16,
}

/// Status of a request.
pub enum Status {
    Active,
    Inactive,
    Error(String),
}

/// A handler trait.
pub trait Handler {
    fn handle(&self, req: Request) -> Response;
}

/// A result alias.
type Result<T> = std::result::Result<T, Error>;

impl Config {
    /// Create a new Config.
    pub fn new(host: String, port: u16) -> Self {
        Config { host, port }
    }

    pub fn address(&self) -> String {
        format!("{}:{}", self.host, self.port)
    }
}

/// A standalone function.
pub fn standalone(x: i32) -> bool {
    x > 0
}

mod inner {
    pub fn nested() {}
}
'''


class TestRustParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        assert result.ok
        assert result.language == "rust"
        assert len(result.content_hash) == 64

    def test_functions_extracted(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        names = {s.name for s in result.symbols}
        assert "standalone" in names
        assert "new" in names
        assert "address" in names

    def test_struct_extracted(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.kind == "struct"
        assert "struct Config" in config.signature

    def test_enum_extracted(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        status = next(s for s in result.symbols if s.name == "Status")
        assert status.kind == "enum"

    def test_trait_extracted(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        handler = next(s for s in result.symbols if s.name == "Handler")
        assert handler.kind == "trait"

    def test_trait_method_extracted(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        handle = next(s for s in result.symbols if s.name == "handle")
        assert handle.kind == "method"
        assert handle.parent_name == "Handler"
        assert handle.qualified_name == "Handler.handle"

    def test_impl_methods(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        new = next(s for s in result.symbols if s.name == "new")
        assert new.kind == "method"
        assert new.parent_name == "Config"
        assert new.qualified_name == "Config.new"

    def test_const_extracted(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        c = next(s for s in result.symbols if s.name == "MAX_RETRIES")
        assert c.kind == "constant"

    def test_static_extracted(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        s = next(s for s in result.symbols if s.name == "DEFAULT_HOST")
        assert s.kind == "static"

    def test_type_alias(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        r = next(s for s in result.symbols if s.name == "Result")
        assert r.kind == "type_alias"

    def test_use_as_imports(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        assert len(result.imports) == 2
        import_texts = {i.name for i in result.imports}
        assert any("HashMap" in t for t in import_texts)
        assert any("Read" in t for t in import_texts)

    def test_module_extracted(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        inner = next(s for s in result.symbols if s.name == "inner")
        assert inner.kind == "module"

    def test_nested_in_module(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        nested = next(s for s in result.symbols if s.name == "nested")
        assert nested.parent_name == "inner"
        assert nested.qualified_name == "inner.nested"

    def test_doc_comments(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.docstring == "Application configuration."
        standalone = next(s for s in result.symbols if s.name == "standalone")
        assert standalone.docstring == "A standalone function."

    def test_impl_method_doc(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        new = next(s for s in result.symbols if s.name == "new")
        assert new.docstring == "Create a new Config."

    def test_function_signatures(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        standalone = next(s for s in result.symbols if s.name == "standalone")
        assert "fn standalone(x: i32)" in standalone.signature
        assert "bool" in standalone.signature

    def test_method_signatures(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        new = next(s for s in result.symbols if s.name == "new")
        assert "fn new(host: String, port: u16)" in new.signature
        assert "Self" in new.signature

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_RUST, "rust")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.start_line > 0
        assert config.end_line >= config.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "rust")
        assert result.ok
        assert len(result.symbols) == 0

    def test_multiline_doc_comment(self):
        source = '''
/// Process incoming data.
/// Validates and transforms.
pub fn process() {}
'''
        result = self.parser.parse_source(source, "rust")
        func = next(s for s in result.symbols if s.name == "process")
        assert "Process incoming data." in func.docstring
        assert "Validates" in func.docstring
