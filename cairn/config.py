"""Configuration management. All settings from environment variables with sensible defaults."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    name: str = "cairn"
    user: str = "cairn"
    password: str = "cairn"

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str = "all-MiniLM-L6-v2"
    dimensions: int = 384


@dataclass(frozen=True)
class LLMConfig:
    backend: str = "ollama"  # "ollama" or "bedrock"

    # Bedrock settings
    bedrock_model: str = "us.meta.llama3-2-90b-instruct-v1:0"
    bedrock_region: str = "us-east-1"

    # Ollama settings
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"


@dataclass(frozen=True)
class LLMCapabilities:
    query_expansion: bool = True
    relationship_extract: bool = True
    rule_conflict_check: bool = True
    session_synthesis: bool = True
    consolidation: bool = True
    confidence_gating: bool = False  # off by default — high reasoning demand
    event_digest: bool = True  # digest event batches via LLM

    def active_list(self) -> list[str]:
        """Return names of enabled capabilities."""
        return [
            name for name in (
                "query_expansion", "relationship_extract", "rule_conflict_check",
                "session_synthesis", "consolidation", "confidence_gating",
                "event_digest",
            )
            if getattr(self, name)
        ]


@dataclass(frozen=True)
class Config:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    capabilities: LLMCapabilities = field(default_factory=LLMCapabilities)
    enrichment_enabled: bool = True
    transport: str = "stdio"  # "stdio" or "http"
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    event_archive_dir: str | None = None  # File-based event archive (e.g. /data/events)


def _parse_cors_origins(raw: str) -> list[str]:
    """Parse comma-separated CORS origins. '*' means allow all."""
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["*"]


def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        db=DatabaseConfig(
            host=os.getenv("CAIRN_DB_HOST", "localhost"),
            port=int(os.getenv("CAIRN_DB_PORT", "5432")),
            name=os.getenv("CAIRN_DB_NAME", "cairn"),
            user=os.getenv("CAIRN_DB_USER", "cairn"),
            password=os.getenv("CAIRN_DB_PASS", "cairn"),
        ),
        embedding=EmbeddingConfig(
            model=os.getenv("CAIRN_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        ),
        llm=LLMConfig(
            backend=os.getenv("CAIRN_LLM_BACKEND", "ollama"),
            bedrock_model=os.getenv("CAIRN_BEDROCK_MODEL", "us.meta.llama3-2-90b-instruct-v1:0"),
            bedrock_region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            ollama_url=os.getenv("CAIRN_OLLAMA_URL", "http://localhost:11434"),
            ollama_model=os.getenv("CAIRN_OLLAMA_MODEL", "qwen2.5-coder:7b"),
        ),
        capabilities=LLMCapabilities(
            query_expansion=os.getenv("CAIRN_LLM_QUERY_EXPANSION", "true").lower() in ("true", "1", "yes"),
            relationship_extract=os.getenv("CAIRN_LLM_RELATIONSHIP_EXTRACT", "true").lower() in ("true", "1", "yes"),
            rule_conflict_check=os.getenv("CAIRN_LLM_RULE_CONFLICT_CHECK", "true").lower() in ("true", "1", "yes"),
            session_synthesis=os.getenv("CAIRN_LLM_SESSION_SYNTHESIS", "true").lower() in ("true", "1", "yes"),
            consolidation=os.getenv("CAIRN_LLM_CONSOLIDATION", "true").lower() in ("true", "1", "yes"),
            confidence_gating=os.getenv("CAIRN_LLM_CONFIDENCE_GATING", "false").lower() in ("true", "1", "yes"),
            event_digest=os.getenv("CAIRN_LLM_EVENT_DIGEST", "true").lower() in ("true", "1", "yes"),
        ),
        enrichment_enabled=os.getenv("CAIRN_ENRICHMENT_ENABLED", "true").lower() in ("true", "1", "yes"),
        transport=os.getenv("CAIRN_TRANSPORT", "stdio"),
        http_host=os.getenv("CAIRN_HTTP_HOST", "0.0.0.0"),
        http_port=int(os.getenv("CAIRN_HTTP_PORT", "8000")),
        cors_origins=_parse_cors_origins(os.getenv("CAIRN_CORS_ORIGINS", "*")),
        event_archive_dir=os.getenv("CAIRN_EVENT_ARCHIVE_DIR") or None,
    )
