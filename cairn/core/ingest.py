"""Smart ingestion pipeline: classify, chunk, dedup, and route content."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from cairn.core.utils import extract_json, get_or_create_project

if TYPE_CHECKING:
    from cairn.config import Config
    from cairn.core.memory import MemoryStore
    from cairn.core.projects import ProjectManager
    from cairn.llm.interface import LLMInterface
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class IngestPipeline:
    """Unified content ingestion: dedup, classify, chunk, store, log."""

    def __init__(
        self,
        db: Database,
        project_manager: ProjectManager,
        memory_store: MemoryStore,
        llm: LLMInterface | None,
        config: Config,
    ):
        self.db = db
        self.project_manager = project_manager
        self.memory_store = memory_store
        self.llm = llm
        self.chunk_size = config.ingest_chunk_size
        self.chunk_overlap = config.ingest_chunk_overlap
        self._chunker = None  # lazy init

    @property
    def chunker(self):
        if self._chunker is None:
            from chonkie import RecursiveChunker
            self._chunker = RecursiveChunker.from_recipe(
                "markdown",
                chunk_size=self.chunk_size,
            )
        return self._chunker

    @staticmethod
    def _validate_url(url: str) -> None:
        """Validate URL before fetching. Blocks SSRF vectors."""
        import ipaddress
        import socket
        from urllib.parse import urlparse

        parsed = urlparse(url)

        # Only allow http/https
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Only http/https URLs allowed, got: {parsed.scheme}")

        if not parsed.hostname:
            raise ValueError("URL must include a hostname")

        # Block known metadata and loopback hosts
        blocked_hosts = {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "169.254.169.254",  # AWS/GCP metadata
            "[::1]",
            "metadata.google.internal",
        }
        if parsed.hostname.lower() in blocked_hosts:
            raise ValueError(f"Fetching from {parsed.hostname} is not allowed")

        # Resolve hostname and block private/reserved IPs
        try:
            resolved = socket.getaddrinfo(parsed.hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for family, _, _, _, sockaddr in resolved:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
                    raise ValueError(f"Fetching from private/reserved IP ({ip}) is not allowed")
        except socket.gaierror:
            pass  # DNS resolution failed — trafilatura will handle the error

    def fetch_url(self, url: str) -> tuple[str, str | None]:
        """Fetch a URL and extract readable content. Returns (content, title)."""
        self._validate_url(url)

        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            raise ValueError(f"Could not fetch URL: {url}")
        text = trafilatura.extract(downloaded)
        if not text:
            raise ValueError(f"Could not extract content from URL: {url}")
        # Get title from a separate metadata extraction
        title = None
        try:
            meta = trafilatura.extract_metadata(downloaded)
            if meta:
                title = meta.title
        except Exception:
            pass
        return text, title

    def ingest(
        self,
        content: str | None = None,
        project: str | None = None,
        hint: str = "auto",
        doc_type: str | None = None,
        title: str | None = None,
        source: str | None = None,
        tags: list[str] | None = None,
        session_name: str | None = None,
        url: str | None = None,
        memory_type: str | None = None,
    ) -> dict:
        """Run the full pipeline. Returns result dict.

        If url is provided and content is empty, fetches and extracts from URL.
        If both url and content, stores content and attaches url as source.
        """
        # 0. URL extraction
        if url and not content:
            content, extracted_title = self.fetch_url(url)
            if not title:
                title = extracted_title
            source = source or url
        elif url and content:
            source = source or url

        if not content:
            raise ValueError("content is required (or provide a url to fetch)")

        # 1. Dedup
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        existing = self._check_dedup(content_hash)
        if existing:
            return {"status": "duplicate", "existing": existing}

        # 2. Classify
        target_type = self._classify(content, hint)

        # 3. Store doc (if doc or both)
        doc_id = None
        if target_type in ("doc", "both"):
            effective_doc_type = doc_type or "guide"
            result = self.project_manager.create_doc(
                project, effective_doc_type, content, title=title,
            )
            doc_id = result["id"]

        # 4. Chunk + store memories (if memory or both)
        memory_ids = []
        chunk_count = 0
        if target_type in ("memory", "both"):
            chunks = self._chunk(content)
            chunk_count = len(chunks)
            for i, chunk in enumerate(chunks):
                mem = self.memory_store.store(
                    content=chunk.text,
                    project=project,
                    memory_type=memory_type or "note",
                    tags=tags,
                    session_name=session_name,
                    source_doc_id=doc_id,
                    enrich=False,
                )
                memory_ids.append(mem["id"])

        # 5. Log
        target_ids = ([doc_id] if doc_id else []) + memory_ids
        self._log(source, project, content_hash, target_type, target_ids, chunk_count)

        return {
            "status": "ingested",
            "target_type": target_type,
            "doc_id": doc_id,
            "memory_ids": memory_ids,
            "chunk_count": chunk_count,
        }

    def _classify(self, content: str, hint: str) -> str:
        """Determine target type: doc, memory, or both."""
        if hint != "auto":
            return hint
        if not self.llm:
            return "memory"

        try:
            from cairn.llm.prompts import build_classification_messages
            messages = build_classification_messages(content[:3000])
            raw = self.llm.generate(messages, max_tokens=64)
            parsed = extract_json(raw, json_type="object")
            if parsed and parsed.get("type") in ("doc", "memory", "both"):
                return parsed["type"]
        except Exception:
            logger.warning("Classification failed, defaulting to memory", exc_info=True)

        return "memory"

    def _chunk(self, content: str) -> list:
        """Split content into chunks. Returns single-element list if small."""
        if len(content) < 2000:
            from dataclasses import dataclass

            @dataclass
            class SingleChunk:
                text: str

            return [SingleChunk(text=content)]

        return self.chunker(content)

    def _check_dedup(self, content_hash: str) -> dict | None:
        """Check if content has already been ingested."""
        row = self.db.execute_one(
            "SELECT id, source, target_type, target_ids, created_at FROM ingestion_log WHERE content_hash = %s",
            (content_hash,),
        )
        if row:
            return {
                "id": row["id"],
                "source": row["source"],
                "target_type": row["target_type"],
                "created_at": row["created_at"].isoformat(),
            }
        return None

    def _log(
        self,
        source: str | None,
        project: str,
        content_hash: str,
        target_type: str,
        target_ids: list[int],
        chunk_count: int,
    ) -> None:
        """Record ingestion in the log for dedup and audit."""
        project_id = get_or_create_project(self.db, project)
        self.db.execute(
            """
            INSERT INTO ingestion_log (source, project_id, content_hash, target_type, target_ids, chunk_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (source, project_id, content_hash, target_type, target_ids, chunk_count),
        )
        self.db.commit()
