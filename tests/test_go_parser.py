"""Tests for Go language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_GO = '''
package main

import (
	"fmt"
	"net/http"
)

// MaxRetries is the maximum number of retries.
const MaxRetries = 3

var DefaultTimeout = 30

// Config holds application configuration.
type Config struct {
	Host string
	Port int
}

// Reader defines a reading interface.
type Reader interface {
	Read(p []byte) (n int, err error)
}

// ID is an alias for string.
type ID = string

// NewConfig creates a new Config with defaults.
func NewConfig() *Config {
	return &Config{Host: "localhost", Port: 8080}
}

// Start launches the server.
func (c *Config) Start() error {
	addr := fmt.Sprintf("%s:%d", c.Host, c.Port)
	return http.ListenAndServe(addr, nil)
}

// Stop shuts down the server gracefully.
func (c Config) Stop() {
	fmt.Println("stopping")
}

func unexported() {
	fmt.Println("internal")
}
'''


class TestGoParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        assert result.ok
        assert result.language == "golang"
        assert len(result.content_hash) == 64

    def test_functions_extracted(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        names = {s.name for s in result.symbols}
        assert "NewConfig" in names
        assert "unexported" in names

    def test_methods_extracted(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "Start" in names
        assert "Stop" in names

    def test_method_parent_name(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        start = next(s for s in result.symbols if s.name == "Start")
        assert start.parent_name == "Config"
        assert start.kind == "method"

    def test_method_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        start = next(s for s in result.symbols if s.name == "Start")
        assert start.qualified_name == "Config.Start"

    def test_value_receiver_method(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        stop = next(s for s in result.symbols if s.name == "Stop")
        assert stop.parent_name == "Config"
        assert stop.kind == "method"

    def test_struct_extracted(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.kind == "struct"

    def test_interface_extracted(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        reader = next(s for s in result.symbols if s.name == "Reader")
        assert reader.kind == "interface"

    def test_type_alias_extracted(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        id_type = next(s for s in result.symbols if s.name == "ID")
        assert id_type.kind == "type_alias"

    def test_constants_extracted(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        c = next(s for s in result.symbols if s.name == "MaxRetries")
        assert c.kind == "constant"

    def test_variables_extracted(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        v = next(s for s in result.symbols if s.name == "DefaultTimeout")
        assert v.kind == "variable"

    def test_imports_extracted(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        assert len(result.imports) == 2
        import_texts = {i.name for i in result.imports}
        assert '"fmt"' in import_texts
        assert '"net/http"' in import_texts

    def test_doc_comments(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.docstring == "Config holds application configuration."
        new_config = next(s for s in result.symbols if s.name == "NewConfig")
        assert new_config.docstring == "NewConfig creates a new Config with defaults."

    def test_method_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        start = next(s for s in result.symbols if s.name == "Start")
        assert start.docstring == "Start launches the server."

    def test_function_signatures(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        new_config = next(s for s in result.symbols if s.name == "NewConfig")
        assert "func NewConfig()" in new_config.signature
        assert "*Config" in new_config.signature

    def test_method_signatures(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        start = next(s for s in result.symbols if s.name == "Start")
        assert "func (Config) Start()" in start.signature
        assert "error" in start.signature

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        config = next(s for s in result.symbols if s.name == "Config")
        assert config.start_line > 0
        assert config.end_line >= config.start_line

    def test_symbol_kinds(self):
        result = self.parser.parse_source(SAMPLE_GO, "golang")
        kind_map = {s.name: s.kind for s in result.symbols}
        assert kind_map["NewConfig"] == "function"
        assert kind_map["Start"] == "method"
        assert kind_map["Config"] == "struct"
        assert kind_map["Reader"] == "interface"
        assert kind_map["MaxRetries"] == "constant"

    def test_empty_file(self):
        result = self.parser.parse_source("package main\n", "golang")
        assert result.ok
        assert len(result.symbols) == 0

    def test_single_import(self):
        source = 'package main\n\nimport "fmt"\n'
        result = self.parser.parse_source(source, "golang")
        assert len(result.imports) == 1

    def test_grouped_const(self):
        source = '''package main

const (
	A = 1
	B = 2
)
'''
        result = self.parser.parse_source(source, "golang")
        names = {s.name for s in result.symbols}
        assert "A" in names
        assert "B" in names
        assert all(s.kind == "constant" for s in result.symbols)

    def test_multiline_doc_comment(self):
        source = '''package main

// ProcessData handles incoming data.
// It validates, transforms, and stores the result.
func ProcessData() {}
'''
        result = self.parser.parse_source(source, "golang")
        func = next(s for s in result.symbols if s.name == "ProcessData")
        assert "ProcessData handles incoming data." in func.docstring
        assert "validates" in func.docstring
