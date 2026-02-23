"""Code summarizer — LLM-generated natural language descriptions for code symbols.

Uses the configurable LLM and embedding engines to generate human-readable
descriptions of code symbols and embed them for semantic search.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.embedding.interface import EmbeddingInterface
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

_DESCRIBE_PROMPT = """\
You are a code documentation assistant. Write a concise 1-2 sentence description of what this code does.

{kind}: {signature}
Docstring: {docstring}
File: {file_path}

Description:"""


class CodeSummarizer:
    """Generate natural language descriptions and embeddings for code symbols."""

    def __init__(self, llm: LLMInterface, embedding: EmbeddingInterface):
        self.llm = llm
        self.embedding = embedding

    def describe_symbol(self, symbol: dict) -> str:
        """Generate a 1-2 sentence NL description of a code symbol.

        Args:
            symbol: Dict with keys: kind, signature, docstring, file_path, name, qualified_name.

        Returns:
            A concise natural language description.
        """
        prompt = _DESCRIBE_PROMPT.format(
            kind=symbol.get("kind", "function"),
            signature=symbol.get("signature", symbol.get("name", "unknown")),
            docstring=symbol.get("docstring") or "None",
            file_path=symbol.get("file_path", "unknown"),
        )

        messages = [{"role": "user", "content": prompt}]
        try:
            response = self.llm.generate(messages, max_tokens=150)
            return response.strip()
        except Exception:
            logger.warning("Failed to describe symbol %s", symbol.get("qualified_name"), exc_info=True)
            # Fallback: use docstring or signature as description
            return symbol.get("docstring") or symbol.get("signature") or symbol.get("name", "")

    def describe_and_embed(self, symbol: dict) -> tuple[str, list[float]]:
        """Generate description + embedding in one call.

        Returns:
            Tuple of (description_text, embedding_vector).
        """
        desc = self.describe_symbol(symbol)
        emb = self.embedding.embed(desc)
        return desc, emb

    def batch_describe(self, symbols: list[dict], project_id: int) -> list[dict]:
        """Describe multiple symbols.

        Returns list of dicts:
            [{qualified_name, file_path, description, embedding}]
        """
        results = []
        # Collect descriptions first
        descriptions = []
        for sym in symbols:
            desc = self.describe_symbol(sym)
            descriptions.append(desc)

        # Batch embed all descriptions at once
        if descriptions:
            embeddings = self.embedding.embed_batch(descriptions)
        else:
            embeddings = []

        for sym, desc, emb in zip(symbols, descriptions, embeddings):
            results.append({
                "qualified_name": sym.get("qualified_name", ""),
                "file_path": sym.get("file_path", ""),
                "description": desc,
                "embedding": emb,
            })

        return results
