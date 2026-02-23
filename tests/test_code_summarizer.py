"""Tests for the code summarizer (LLM descriptions + embeddings).

Uses mocked LLM and embedding engines since they may not be available in CI.
"""

from unittest.mock import MagicMock, patch

from cairn.code.summarizer import CodeSummarizer


class TestCodeSummarizer:

    def _make_mocks(self):
        """Create mock LLM and embedding engine."""
        llm = MagicMock()
        llm.generate.return_value = "Computes the sum of two numbers."

        embedding = MagicMock()
        embedding.embed.return_value = [0.1] * 1024
        embedding.embed_batch.return_value = [[0.1] * 1024, [0.2] * 1024]

        return llm, embedding

    def _make_symbol(self, **overrides):
        """Create a sample symbol dict."""
        base = {
            "name": "add",
            "qualified_name": "add",
            "kind": "function",
            "file_path": "src/utils.py",
            "signature": "def add(a: int, b: int) -> int",
            "docstring": "Add two numbers.",
            "start_line": 1,
            "end_line": 3,
        }
        base.update(overrides)
        return base

    def test_describe_symbol(self):
        llm, embedding = self._make_mocks()
        summarizer = CodeSummarizer(llm, embedding)

        sym = self._make_symbol()
        desc = summarizer.describe_symbol(sym)

        assert desc == "Computes the sum of two numbers."
        assert llm.generate.called

        # Check prompt includes symbol info
        call_args = llm.generate.call_args
        prompt = call_args[0][0][0]["content"]
        assert "function" in prompt
        assert "def add" in prompt

    def test_describe_and_embed(self):
        llm, embedding = self._make_mocks()
        summarizer = CodeSummarizer(llm, embedding)

        sym = self._make_symbol()
        desc, emb = summarizer.describe_and_embed(sym)

        assert desc == "Computes the sum of two numbers."
        assert len(emb) == 1024
        assert embedding.embed.called

    def test_batch_describe(self):
        llm, embedding = self._make_mocks()
        summarizer = CodeSummarizer(llm, embedding)

        syms = [
            self._make_symbol(name="add", qualified_name="add"),
            self._make_symbol(name="subtract", qualified_name="subtract",
                            signature="def subtract(a: int, b: int) -> int"),
        ]

        results = summarizer.batch_describe(syms, project_id=1)

        assert len(results) == 2
        assert results[0]["qualified_name"] == "add"
        assert results[0]["description"] == "Computes the sum of two numbers."
        assert len(results[0]["embedding"]) == 1024
        assert results[1]["qualified_name"] == "subtract"

        # Should use batch embedding
        assert embedding.embed_batch.called

    def test_describe_symbol_fallback_on_error(self):
        """If LLM fails, should fall back to docstring or signature."""
        llm, embedding = self._make_mocks()
        llm.generate.side_effect = Exception("LLM unavailable")

        summarizer = CodeSummarizer(llm, embedding)
        sym = self._make_symbol()
        desc = summarizer.describe_symbol(sym)

        # Should fall back to docstring
        assert desc == "Add two numbers."

    def test_describe_symbol_fallback_no_docstring(self):
        """If LLM fails and no docstring, should fall back to signature."""
        llm, embedding = self._make_mocks()
        llm.generate.side_effect = Exception("LLM unavailable")

        summarizer = CodeSummarizer(llm, embedding)
        sym = self._make_symbol(docstring=None)
        desc = summarizer.describe_symbol(sym)

        assert "def add" in desc

    def test_batch_describe_empty(self):
        llm, embedding = self._make_mocks()
        embedding.embed_batch.return_value = []

        summarizer = CodeSummarizer(llm, embedding)
        results = summarizer.batch_describe([], project_id=1)

        assert results == []
        assert not llm.generate.called

    def test_prompt_includes_kind_and_file(self):
        llm, embedding = self._make_mocks()
        summarizer = CodeSummarizer(llm, embedding)

        sym = self._make_symbol(
            kind="class",
            signature="class UserService",
            file_path="src/services/user.py",
        )
        summarizer.describe_symbol(sym)

        prompt = llm.generate.call_args[0][0][0]["content"]
        assert "class" in prompt
        assert "class UserService" in prompt
        assert "src/services/user.py" in prompt
