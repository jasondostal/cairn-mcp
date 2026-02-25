"""Tests for Bash language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_BASH = '''#!/bin/bash

# Deploy script for the application
# Handles building and deploying

export APP_NAME="myapp"
export APP_PORT=8080

DB_HOST="localhost"

# Build the application
build_app() {
    echo "Building"
    make build
}

# Deploy to production
deploy() {
    local env=$1
    echo "Deploying to $env"
}

source ./config.sh
. ./utils.sh
'''


class TestBashParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        assert result.ok
        assert result.language == "bash"
        assert len(result.content_hash) == 64

    def test_functions_extracted(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        func_names = {s.name for s in result.symbols if s.kind == "function"}
        assert "build_app" in func_names
        assert "deploy" in func_names

    def test_function_signatures(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        build = next(s for s in result.symbols if s.name == "build_app")
        assert build.signature == "build_app()"

    def test_exported_variables(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        var_names = {s.name for s in result.symbols if s.kind == "variable"}
        assert "APP_NAME" in var_names
        assert "APP_PORT" in var_names

    def test_local_variables(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        var_names = {s.name for s in result.symbols if s.kind == "variable"}
        assert "DB_HOST" in var_names

    def test_source_imports(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        assert len(result.imports) == 2
        import_names = {i.name for i in result.imports}
        assert "./config.sh" in import_names
        assert "./utils.sh" in import_names

    def test_source_import_kind(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        for imp in result.imports:
            assert imp.kind == "import"

    def test_doc_comments(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        build = next(s for s in result.symbols if s.name == "build_app")
        assert build.docstring == "Build the application"

    def test_multiline_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        # The export APP_NAME should pick up the multiline comment
        app_name = next(s for s in result.symbols if s.name == "APP_NAME")
        assert "Deploy script" in app_name.docstring
        assert "building and deploying" in app_name.docstring

    def test_function_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        deploy = next(s for s in result.symbols if s.name == "deploy")
        assert deploy.docstring == "Deploy to production"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        build = next(s for s in result.symbols if s.name == "build_app")
        assert build.start_line > 0
        assert build.end_line >= build.start_line

    def test_symbol_kinds(self):
        result = self.parser.parse_source(SAMPLE_BASH, "bash")
        kind_map = {s.name: s.kind for s in result.symbols}
        assert kind_map["build_app"] == "function"
        assert kind_map["deploy"] == "function"
        assert kind_map["APP_NAME"] == "variable"
        assert kind_map["DB_HOST"] == "variable"

    def test_empty_file(self):
        result = self.parser.parse_source("#!/bin/bash\n", "bash")
        assert result.ok
        assert len(result.symbols) == 0

    def test_function_without_comment(self):
        source = '''#!/bin/bash
helper() {
    echo "no doc"
}
'''
        result = self.parser.parse_source(source, "bash")
        helper = next(s for s in result.symbols if s.name == "helper")
        assert helper.docstring is None
        assert helper.kind == "function"
