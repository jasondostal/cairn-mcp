"""Tests for PHP language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_PHP = '''<?php
namespace App\\Services;

use App\\Models\\Config;
use App\\Contracts\\Handler;

/** Max retries constant. */
const MAX_RETRIES = 3;

/**
 * Application configuration.
 */
class ConfigService {
    private const DEFAULT_PORT = 8080;

    /**
     * Create a new config.
     */
    public function __construct(string $host) {
        $this->host = $host;
    }

    public function getHost(): string {
        return $this->host;
    }
}

/**
 * A handler interface.
 */
interface HandlerInterface {
    public function handle(Request $req): Response;
}

enum Status {
    case Active;
    case Inactive;
}

trait Loggable {
    public function log(string $msg): void {}
}

function standalone(int $x): bool {
    return $x > 0;
}
?>'''


class TestPhpParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        assert result.ok
        assert result.language == "php"

    def test_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        cs = next(s for s in result.symbols if s.name == "ConfigService")
        assert cs.kind == "class"

    def test_interface_extracted(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        h = next(s for s in result.symbols if s.name == "HandlerInterface")
        assert h.kind == "interface"

    def test_enum_extracted(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        s = next(s for s in result.symbols if s.name == "Status")
        assert s.kind == "enum"

    def test_trait_extracted(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        t = next(s for s in result.symbols if s.name == "Loggable")
        assert t.kind == "trait"

    def test_function_extracted(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        f = next(s for s in result.symbols if s.name == "standalone")
        assert f.kind == "function"

    def test_constructor(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        ctor = next(s for s in result.symbols if s.name == "__construct")
        assert ctor.kind == "method"
        assert ctor.parent_name == "ConfigService"

    def test_method_extracted(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        m = next(s for s in result.symbols if s.name == "getHost")
        assert m.kind == "method"
        assert m.parent_name == "ConfigService"

    def test_interface_method(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        h = next(s for s in result.symbols if s.name == "handle")
        assert h.kind == "method"
        assert h.parent_name == "HandlerInterface"

    def test_constant(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        c = next(s for s in result.symbols if s.name == "MAX_RETRIES")
        assert c.kind == "constant"

    def test_class_constant(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        c = next(s for s in result.symbols if s.name == "DEFAULT_PORT")
        assert c.kind == "constant"
        assert c.parent_name == "ConfigService"

    def test_use_as_imports(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        assert len(result.imports) == 2
        import_texts = {i.name for i in result.imports}
        assert any("Config" in t for t in import_texts)
        assert any("Handler" in t for t in import_texts)

    def test_phpdoc(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        cs = next(s for s in result.symbols if s.name == "ConfigService")
        assert cs.docstring == "Application configuration."

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_PHP, "php")
        cs = next(s for s in result.symbols if s.name == "ConfigService")
        assert cs.start_line > 0
        assert cs.end_line >= cs.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("<?php ?>", "php")
        assert result.ok
        assert len(result.symbols) == 0
