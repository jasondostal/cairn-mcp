"""Configuration management. All settings from environment variables with sensible defaults."""

import os
from dataclasses import dataclass, field

from cairn.graph.config import Neo4jConfig


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    name: str = "cairn"
    user: str = "cairn"
    password: str = "cairn-dev-password"

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass(frozen=True)
class EmbeddingConfig:
    backend: str = "local"  # "local", "bedrock", "openai", or registered provider name
    model: str = "all-MiniLM-L6-v2"
    dimensions: int = 384

    # Bedrock settings (Titan Text Embeddings V2)
    bedrock_model: str = "amazon.titan-embed-text-v2:0"
    bedrock_region: str = "us-east-1"

    # OpenAI-compatible settings (works with OpenAI, Ollama, vLLM, LM Studio, Together)
    openai_base_url: str = "https://api.openai.com"
    openai_model: str = "text-embedding-3-small"
    openai_api_key: str = ""  # empty = no Authorization header (for local endpoints)


@dataclass(frozen=True)
class LLMConfig:
    backend: str = "ollama"  # "ollama", "bedrock", "gemini", "openai", or registered name

    # Bedrock settings
    bedrock_model: str = "us.meta.llama3-2-90b-instruct-v1:0"
    bedrock_region: str = "us-east-1"

    # Ollama settings
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"

    # Gemini settings
    gemini_model: str = "gemini-2.0-flash"
    gemini_api_key: str = ""

    # OpenAI-compatible settings (works with OpenAI, Groq, Together, Mistral, LM Studio, vLLM)
    openai_base_url: str = "https://api.openai.com"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str = ""


@dataclass(frozen=True)
class LLMCapabilities:
    query_expansion: bool = True
    relationship_extract: bool = True
    rule_conflict_check: bool = True
    session_synthesis: bool = True
    consolidation: bool = True
    confidence_gating: bool = False  # off by default — high reasoning demand
    event_digest: bool = True  # digest event batches via LLM
    reranking: bool = False  # off by default — cross-encoder reranking
    type_routing: bool = False  # off by default — query intent classification + type boost
    spreading_activation: bool = False  # off by default — graph-based retrieval
    mca_gate: bool = False  # off by default — keyword coverage pre-filter (MCA)
    knowledge_extraction: bool = False  # off by default — combined extraction + Neo4j graph
    search_v2: bool = False  # off by default — intent-routed search with graph handlers

    def active_list(self) -> list[str]:
        """Return names of enabled capabilities."""
        return [
            name for name in (
                "query_expansion", "relationship_extract", "rule_conflict_check",
                "session_synthesis", "consolidation", "confidence_gating",
                "event_digest", "reranking", "type_routing", "spreading_activation",
                "mca_gate", "knowledge_extraction", "search_v2",
            )
            if getattr(self, name)
        ]


@dataclass(frozen=True)
class AuthConfig:
    enabled: bool = False
    api_key: str | None = None  # Static API key (checked via X-API-Key header)
    header_name: str = "X-API-Key"  # Header to check for auth token


@dataclass(frozen=True)
class AnalyticsConfig:
    enabled: bool = True
    retention_days: int = 90
    # Cost rates per 1k tokens (USD)
    cost_embedding_per_1k: float = 0.0001
    cost_llm_input_per_1k: float = 0.003
    cost_llm_output_per_1k: float = 0.015


@dataclass(frozen=True)
class Config:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    capabilities: LLMCapabilities = field(default_factory=LLMCapabilities)
    auth: AuthConfig = field(default_factory=AuthConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    enrichment_enabled: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_candidates: int = 50  # widen RRF pool when reranking is on
    transport: str = "stdio"  # "stdio" or "http"
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    event_archive_dir: str | None = None  # File-based event archive (e.g. /data/events)
    ingest_chunk_size: int = 512       # tokens per chunk (Chonkie)
    ingest_chunk_overlap: int = 64     # overlap tokens between chunks


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
            password=os.getenv("CAIRN_DB_PASS", "cairn-dev-password"),
        ),
        embedding=EmbeddingConfig(
            backend=os.getenv("CAIRN_EMBEDDING_BACKEND", "local"),
            model=os.getenv("CAIRN_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            dimensions=int(os.getenv("CAIRN_EMBEDDING_DIMENSIONS", "384")),
            bedrock_model=os.getenv("CAIRN_EMBEDDING_BEDROCK_MODEL", "amazon.titan-embed-text-v2:0"),
            bedrock_region=os.getenv("CAIRN_EMBEDDING_BEDROCK_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
            openai_base_url=os.getenv("CAIRN_EMBEDDING_OPENAI_URL", os.getenv("CAIRN_OPENAI_BASE_URL", "https://api.openai.com")),
            openai_model=os.getenv("CAIRN_EMBEDDING_OPENAI_MODEL", "text-embedding-3-small"),
            openai_api_key=os.getenv("CAIRN_EMBEDDING_OPENAI_KEY", os.getenv("CAIRN_OPENAI_API_KEY", "")),
        ),
        llm=LLMConfig(
            backend=os.getenv("CAIRN_LLM_BACKEND", "ollama"),
            bedrock_model=os.getenv("CAIRN_BEDROCK_MODEL", "us.meta.llama3-2-90b-instruct-v1:0"),
            bedrock_region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            ollama_url=os.getenv("CAIRN_OLLAMA_URL", "http://localhost:11434"),
            ollama_model=os.getenv("CAIRN_OLLAMA_MODEL", "qwen2.5-coder:7b"),
            gemini_model=os.getenv("CAIRN_GEMINI_MODEL", "gemini-2.0-flash"),
            gemini_api_key=os.getenv("CAIRN_GEMINI_API_KEY", ""),
            openai_base_url=os.getenv("CAIRN_OPENAI_BASE_URL", "https://api.openai.com"),
            openai_model=os.getenv("CAIRN_OPENAI_MODEL", "gpt-4o-mini"),
            openai_api_key=os.getenv("CAIRN_OPENAI_API_KEY", ""),
        ),
        capabilities=LLMCapabilities(
            query_expansion=os.getenv("CAIRN_LLM_QUERY_EXPANSION", "true").lower() in ("true", "1", "yes"),
            relationship_extract=os.getenv("CAIRN_LLM_RELATIONSHIP_EXTRACT", "true").lower() in ("true", "1", "yes"),
            rule_conflict_check=os.getenv("CAIRN_LLM_RULE_CONFLICT_CHECK", "true").lower() in ("true", "1", "yes"),
            session_synthesis=os.getenv("CAIRN_LLM_SESSION_SYNTHESIS", "true").lower() in ("true", "1", "yes"),
            consolidation=os.getenv("CAIRN_LLM_CONSOLIDATION", "true").lower() in ("true", "1", "yes"),
            confidence_gating=os.getenv("CAIRN_LLM_CONFIDENCE_GATING", "false").lower() in ("true", "1", "yes"),
            event_digest=os.getenv("CAIRN_LLM_EVENT_DIGEST", "true").lower() in ("true", "1", "yes"),
            reranking=os.getenv("CAIRN_RERANKING", "false").lower() in ("true", "1", "yes"),
            type_routing=os.getenv("CAIRN_TYPE_ROUTING", "false").lower() in ("true", "1", "yes"),
            spreading_activation=os.getenv("CAIRN_SPREADING_ACTIVATION", "false").lower() in ("true", "1", "yes"),
            mca_gate=os.getenv("CAIRN_MCA_GATE", "false").lower() in ("true", "1", "yes"),
            knowledge_extraction=os.getenv("CAIRN_KNOWLEDGE_EXTRACTION", "false").lower() in ("true", "1", "yes"),
            search_v2=os.getenv("CAIRN_SEARCH_V2", "false").lower() in ("true", "1", "yes"),
        ),
        auth=AuthConfig(
            enabled=os.getenv("CAIRN_AUTH_ENABLED", "false").lower() in ("true", "1", "yes"),
            api_key=os.getenv("CAIRN_API_KEY") or None,
            header_name=os.getenv("CAIRN_AUTH_HEADER", "X-API-Key"),
        ),
        analytics=AnalyticsConfig(
            enabled=os.getenv("CAIRN_ANALYTICS_ENABLED", "true").lower() in ("true", "1", "yes"),
            retention_days=int(os.getenv("CAIRN_ANALYTICS_RETENTION_DAYS", "90")),
            cost_embedding_per_1k=float(os.getenv("CAIRN_ANALYTICS_COST_EMBEDDING", "0.0001")),
            cost_llm_input_per_1k=float(os.getenv("CAIRN_ANALYTICS_COST_LLM_INPUT", "0.003")),
            cost_llm_output_per_1k=float(os.getenv("CAIRN_ANALYTICS_COST_LLM_OUTPUT", "0.015")),
        ),
        neo4j=Neo4jConfig(
            uri=os.getenv("CAIRN_NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("CAIRN_NEO4J_USER", "neo4j"),
            password=os.getenv("CAIRN_NEO4J_PASSWORD", "cairn-dev-password"),
            database=os.getenv("CAIRN_NEO4J_DATABASE", "neo4j"),
        ),
        enrichment_enabled=os.getenv("CAIRN_ENRICHMENT_ENABLED", "true").lower() in ("true", "1", "yes"),
        reranker_model=os.getenv("CAIRN_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
        rerank_candidates=int(os.getenv("CAIRN_RERANK_CANDIDATES", "50")),
        transport=os.getenv("CAIRN_TRANSPORT", "stdio"),
        http_host=os.getenv("CAIRN_HTTP_HOST", "0.0.0.0"),
        http_port=int(os.getenv("CAIRN_HTTP_PORT", "8000")),
        cors_origins=_parse_cors_origins(os.getenv("CAIRN_CORS_ORIGINS", "*")),
        event_archive_dir=os.getenv("CAIRN_EVENT_ARCHIVE_DIR") or None,
        ingest_chunk_size=int(os.getenv("CAIRN_INGEST_CHUNK_SIZE", "512")),
        ingest_chunk_overlap=int(os.getenv("CAIRN_INGEST_CHUNK_OVERLAP", "64")),
    )
