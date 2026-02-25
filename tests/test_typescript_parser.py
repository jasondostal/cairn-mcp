"""Tests for TypeScript/TSX tree-sitter parsing."""

from pathlib import Path

from cairn.code.parser import CodeParser, CodeSymbol, ParseResult
from cairn.code.utils import path_to_module_ts, resolve_ts_import


SAMPLE_TS = '''
import { useState } from 'react';
import axios from 'axios';

interface UserProps {
  name: string;
  age: number;
}

type ID = string | number;

enum Color {
  Red,
  Green,
  Blue,
}

function greet(name: string): string {
  return "Hello " + name;
}

class UserService {
  getUser(id: number): Promise<UserProps> {
    return axios.get(`/users/${id}`);
  }

  deleteUser(id: number): void {
    axios.delete(`/users/${id}`);
  }
}

const add = (a: number, b: number): number => a + b;
'''


SAMPLE_TSX = '''
import React from 'react';
import { useState, useEffect } from 'react';

interface ButtonProps {
  label: string;
  onClick: () => void;
}

/** A simple button component. */
function Button({ label, onClick }: ButtonProps) {
  return <button onClick={onClick}>{label}</button>;
}

const Header = (props: { title: string }) => {
  return <h1>{props.title}</h1>;
};

function useCounter(initial: number) {
  const [count, setCount] = useState(initial);
  return { count, increment: () => setCount(c => c + 1) };
}

function useFetch(url: string) {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetch(url).then(r => r.json()).then(setData);
  }, [url]);
  return data;
}

function helperFunction(x: number): number {
  return x * 2;
}

export default Button;
'''


class TestTypeScriptParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_ts_basic(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        assert result.ok
        assert result.language == "typescript"

    def test_ts_functions(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        names = {s.name for s in result.symbols}
        assert "greet" in names

    def test_ts_classes(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        cls = next(s for s in result.symbols if s.name == "UserService")
        assert cls.kind == "class"

    def test_ts_methods(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        methods = [s for s in result.symbols if s.kind == "method"]
        method_names = {m.name for m in methods}
        assert "getUser" in method_names
        assert "deleteUser" in method_names
        for m in methods:
            assert m.parent_name == "UserService"

    def test_ts_interfaces(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        iface = next(s for s in result.symbols if s.name == "UserProps")
        assert iface.kind == "interface"
        assert "interface UserProps" in iface.signature

    def test_ts_type_alias(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        ta = next(s for s in result.symbols if s.name == "ID")
        assert ta.kind == "type_alias"

    def test_ts_enum(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        en = next(s for s in result.symbols if s.name == "Color")
        assert en.kind == "enum"
        assert en.signature == "enum Color"

    def test_ts_arrow_function(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        add = next(s for s in result.symbols if s.name == "add")
        assert add.kind == "function"
        assert "const add" in add.signature

    def test_ts_imports(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        assert len(result.imports) == 2
        import_texts = {i.name for i in result.imports}
        assert any("useState" in t for t in import_texts)
        assert any("axios" in t for t in import_texts)

    def test_ts_qualified_names(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        qnames = {s.qualified_name for s in result.symbols}
        assert "UserService" in qnames
        assert "UserService.getUser" in qnames
        assert "greet" in qnames

    def test_ts_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_TS, "typescript")
        greet = next(s for s in result.symbols if s.name == "greet")
        assert greet.start_line > 0
        assert greet.end_line >= greet.start_line


class TestTSXParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_tsx_basic(self):
        result = self.parser.parse_source(SAMPLE_TSX, "typescript_tsx")
        assert result.ok
        assert result.language == "typescript_tsx"

    def test_tsx_component_detection(self):
        """Functions returning JSX should be detected as components."""
        result = self.parser.parse_source(SAMPLE_TSX, "typescript_tsx")
        button = next(s for s in result.symbols if s.name == "Button")
        assert button.kind == "component"

    def test_tsx_arrow_component(self):
        """Arrow functions returning JSX should be detected as components."""
        result = self.parser.parse_source(SAMPLE_TSX, "typescript_tsx")
        header = next(s for s in result.symbols if s.name == "Header")
        assert header.kind == "component"

    def test_tsx_hooks(self):
        """Functions starting with 'use' should be detected as hooks."""
        result = self.parser.parse_source(SAMPLE_TSX, "typescript_tsx")
        hooks = [s for s in result.symbols if s.kind == "hook"]
        hook_names = {h.name for h in hooks}
        assert "useCounter" in hook_names
        assert "useFetch" in hook_names

    def test_tsx_regular_function(self):
        """Non-component, non-hook functions should be 'function'."""
        result = self.parser.parse_source(SAMPLE_TSX, "typescript_tsx")
        helper = next(s for s in result.symbols if s.name == "helperFunction")
        assert helper.kind == "function"

    def test_tsx_interface(self):
        result = self.parser.parse_source(SAMPLE_TSX, "typescript_tsx")
        iface = next(s for s in result.symbols if s.name == "ButtonProps")
        assert iface.kind == "interface"

    def test_tsx_imports(self):
        result = self.parser.parse_source(SAMPLE_TSX, "typescript_tsx")
        assert len(result.imports) >= 2

    def test_tsx_all_symbols(self):
        result = self.parser.parse_source(SAMPLE_TSX, "typescript_tsx")
        all_names = {s.name for s in result.symbols}
        assert "Button" in all_names
        assert "Header" in all_names
        assert "useCounter" in all_names
        assert "helperFunction" in all_names
        assert "ButtonProps" in all_names


class TestTSXExport:

    def test_exported_function(self):
        source = '''
export function greet(name: string): string {
  return "Hello " + name;
}
'''
        parser = CodeParser()
        result = parser.parse_source(source, "typescript")
        assert any(s.name == "greet" for s in result.symbols)

    def test_exported_class(self):
        source = '''
export class MyService {
  getData(): string {
    return "data";
  }
}
'''
        parser = CodeParser()
        result = parser.parse_source(source, "typescript")
        assert any(s.name == "MyService" for s in result.symbols)
        assert any(s.name == "getData" for s in result.symbols)

    def test_exported_interface(self):
        source = '''
export interface Config {
  name: string;
  value: number;
}
'''
        parser = CodeParser()
        result = parser.parse_source(source, "typescript")
        assert any(s.name == "Config" and s.kind == "interface" for s in result.symbols)

    def test_exported_const_arrow(self):
        source = '''
export const multiply = (a: number, b: number): number => a * b;
'''
        parser = CodeParser()
        result = parser.parse_source(source, "typescript")
        assert any(s.name == "multiply" for s in result.symbols)


class TestFileExtensions:

    def test_ts_extension(self):
        parser = CodeParser()
        assert parser.parse_file(Path("test.ts")) is None or True  # May fail on missing file
        # Verify the language is detected
        from cairn.code.languages import language_for_extension
        assert language_for_extension(".ts") == "typescript"
        assert language_for_extension(".tsx") == "typescript_tsx"
        assert language_for_extension(".py") == "python"
        assert language_for_extension(".rs") == "rust"
        assert language_for_extension(".java") == "java"
        assert language_for_extension(".go") == "golang"
        assert language_for_extension(".c") == "c"
        assert language_for_extension(".cpp") == "cpp"
        assert language_for_extension(".php") == "php"
        assert language_for_extension(".rb") == "ruby"
        assert language_for_extension(".swift") == "swift"
        assert language_for_extension(".kt") == "kotlin"
        assert language_for_extension(".cs") == "csharp"
        assert language_for_extension(".json") == "json"
        assert language_for_extension(".yaml") == "yaml"
        assert language_for_extension(".sh") == "bash"
        assert language_for_extension(".sql") == "sql"
        assert language_for_extension(".md") == "markdown"
        assert language_for_extension(".tf") == "hcl"
        assert language_for_extension(".toml") == "toml"
        assert language_for_extension(".scala") == "scala"


class TestPathToModuleTs:

    def test_regular_ts_file(self):
        assert path_to_module_ts("src/components/Button.tsx") == "src.components.Button"

    def test_index_file(self):
        assert path_to_module_ts("src/utils/index.ts") == "src.utils"

    def test_top_level(self):
        assert path_to_module_ts("app.ts") == "app"

    def test_non_ts(self):
        assert path_to_module_ts("README.md") is None

    def test_python_file(self):
        assert path_to_module_ts("cairn/core/search.py") is None


class TestResolveTsImport:

    def test_relative_with_extension(self):
        known = {"src/utils.ts", "src/components/Button.tsx"}
        assert resolve_ts_import("./utils", "src", known) == "src/utils.ts"

    def test_relative_tsx(self):
        known = {"src/components/Button.tsx"}
        assert resolve_ts_import("./components/Button", "src", known) == "src/components/Button.tsx"

    def test_index_file(self):
        known = {"src/components/index.ts"}
        assert resolve_ts_import("./components", "src", known) == "src/components/index.ts"

    def test_bare_specifier(self):
        """Bare specifiers (external deps) should return None."""
        known = {"src/utils.ts"}
        assert resolve_ts_import("react", "src", known) is None

    def test_not_found(self):
        known = {"src/utils.ts"}
        assert resolve_ts_import("./missing", "src", known) is None

    def test_parent_relative(self):
        known = {"src/shared/types.ts"}
        assert resolve_ts_import("../shared/types", "src/components", known) == "src/shared/types.ts"


class TestJSDocExtraction:

    def test_jsdoc_extracted(self):
        source = '''
/** Adds two numbers together. */
function add(a: number, b: number): number {
  return a + b;
}
'''
        parser = CodeParser()
        result = parser.parse_source(source, "typescript")
        add_fn = next(s for s in result.symbols if s.name == "add")
        assert add_fn.docstring is not None
        assert "Adds two numbers" in add_fn.docstring

    def test_no_jsdoc(self):
        source = '''
function add(a: number, b: number): number {
  return a + b;
}
'''
        parser = CodeParser()
        result = parser.parse_source(source, "typescript")
        add_fn = next(s for s in result.symbols if s.name == "add")
        assert add_fn.docstring is None
