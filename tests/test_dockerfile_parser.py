"""Tests for Dockerfile language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_DOCKERFILE = '''# Build stage
FROM python:3.12-slim AS builder

ARG APP_VERSION=1.0.0
ENV PYTHONUNBUFFERED=1

RUN pip install poetry
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-dev

# Runtime stage
FROM python:3.12-slim AS runtime

LABEL maintainer="dev@example.com"
LABEL version="1.0"

COPY --from=builder /app /app
WORKDIR /app

ENV APP_ENV=production
EXPOSE 8080
EXPOSE 9090/tcp

CMD ["python", "main.py"]
'''


class TestDockerfileParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        assert result.ok
        assert result.language == "dockerfile"
        assert len(result.content_hash) == 64

    def test_from_stages_extracted(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        stages = [s for s in result.symbols if s.kind == "stage"]
        assert len(stages) == 2

    def test_from_aliases(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        stages = [s for s in result.symbols if s.kind == "stage"]
        names = {s.name for s in stages}
        assert "builder" in names
        assert "runtime" in names

    def test_from_signature(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        builder = next(s for s in result.symbols if s.name == "builder")
        assert "FROM python:3.12-slim AS builder" in builder.signature

    def test_env_extracted(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        envs = [s for s in result.symbols if s.kind == "env"]
        env_names = {s.name for s in envs}
        assert "PYTHONUNBUFFERED" in env_names
        assert "APP_ENV" in env_names

    def test_expose_extracted(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        exposes = [s for s in result.symbols if s.kind == "expose"]
        assert len(exposes) == 2
        ports = {s.name for s in exposes}
        assert "8080" in ports
        assert "9090/tcp" in ports

    def test_expose_signature(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        expose = next(s for s in result.symbols if s.name == "8080")
        assert expose.signature == "EXPOSE 8080"

    def test_label_extracted(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        labels = [s for s in result.symbols if s.kind == "label"]
        label_names = {s.name for s in labels}
        assert "maintainer" in label_names
        assert "version" in label_names

    def test_arg_extracted(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        args = [s for s in result.symbols if s.kind == "arg"]
        assert len(args) == 1
        assert args[0].name == "APP_VERSION"

    def test_from_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        builder = next(s for s in result.symbols if s.name == "builder")
        assert builder.docstring == "Build stage"

    def test_runtime_stage_comment(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        runtime = next(s for s in result.symbols if s.name == "runtime")
        assert runtime.docstring == "Runtime stage"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        builder = next(s for s in result.symbols if s.name == "builder")
        assert builder.start_line > 0
        assert builder.end_line >= builder.start_line

    def test_symbol_kinds(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        kinds = {s.kind for s in result.symbols}
        assert "stage" in kinds
        assert "env" in kinds
        assert "expose" in kinds
        assert "label" in kinds
        assert "arg" in kinds

    def test_empty_dockerfile(self):
        result = self.parser.parse_source("# empty\n", "dockerfile")
        assert result.ok
        assert len(result.symbols) == 0

    def test_from_without_alias(self):
        source = "FROM ubuntu:22.04\n"
        result = self.parser.parse_source(source, "dockerfile")
        stages = [s for s in result.symbols if s.kind == "stage"]
        assert len(stages) == 1
        assert stages[0].name == "ubuntu:22.04"
        assert stages[0].signature == "FROM ubuntu:22.04"

    def test_arg_signature(self):
        result = self.parser.parse_source(SAMPLE_DOCKERFILE, "dockerfile")
        arg = next(s for s in result.symbols if s.kind == "arg")
        assert "ARG APP_VERSION" in arg.signature
