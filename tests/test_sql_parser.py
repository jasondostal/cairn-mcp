"""Tests for SQL language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_SQL = '''-- Users table for authentication
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE
);

/* Active users view
   Shows only non-deleted users */
CREATE VIEW active_users AS
SELECT * FROM users WHERE deleted_at IS NULL;

-- Calculate user age
CREATE FUNCTION get_user_age(user_id INT)
RETURNS INT AS
BEGIN
    RETURN 0;
END;

CREATE INDEX idx_users_email ON users(email);

-- Audit trigger
CREATE TRIGGER users_audit
AFTER INSERT ON users
FOR EACH ROW EXECUTE FUNCTION audit_log();
'''


class TestSqlParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        assert result.ok
        assert result.language == "sql"
        assert len(result.content_hash) == 64

    def test_create_table_extracted(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        tables = [s for s in result.symbols if s.kind == "table"]
        assert len(tables) == 1
        assert tables[0].name == "users"

    def test_create_view_extracted(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        views = [s for s in result.symbols if s.kind == "view"]
        assert len(views) == 1
        assert views[0].name == "active_users"

    def test_create_function_extracted(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        funcs = [s for s in result.symbols if s.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "get_user_age"

    def test_create_index_extracted(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        indexes = [s for s in result.symbols if s.kind == "index"]
        assert len(indexes) == 1
        assert indexes[0].name == "idx_users_email"

    def test_create_trigger_extracted(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        triggers = [s for s in result.symbols if s.kind == "trigger"]
        assert len(triggers) == 1
        assert triggers[0].name == "users_audit"

    def test_table_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        users = next(s for s in result.symbols if s.name == "users")
        assert users.docstring == "Users table for authentication"

    def test_view_block_comment(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        view = next(s for s in result.symbols if s.name == "active_users")
        assert "Active users view" in view.docstring
        assert "non-deleted users" in view.docstring

    def test_function_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        func = next(s for s in result.symbols if s.name == "get_user_age")
        assert func.docstring == "Calculate user age"

    def test_trigger_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        trigger = next(s for s in result.symbols if s.name == "users_audit")
        assert trigger.docstring == "Audit trigger"

    def test_table_signature(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        users = next(s for s in result.symbols if s.name == "users")
        assert "CREATE TABLE users" in users.signature

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        users = next(s for s in result.symbols if s.name == "users")
        assert users.start_line > 0
        assert users.end_line >= users.start_line

    def test_symbol_kinds(self):
        result = self.parser.parse_source(SAMPLE_SQL, "sql")
        kind_map = {s.name: s.kind for s in result.symbols}
        assert kind_map["users"] == "table"
        assert kind_map["active_users"] == "view"
        assert kind_map["get_user_age"] == "function"
        assert kind_map["idx_users_email"] == "index"
        assert kind_map["users_audit"] == "trigger"

    def test_empty_file(self):
        result = self.parser.parse_source("-- empty\n", "sql")
        assert result.ok
        assert len(result.symbols) == 0

    def test_simple_create_table(self):
        source = "CREATE TABLE orders (id INT);\n"
        result = self.parser.parse_source(source, "sql")
        assert len(result.symbols) == 1
        assert result.symbols[0].name == "orders"
        assert result.symbols[0].kind == "table"
