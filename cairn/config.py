"""Configuration management. All settings from environment variables with sensible defaults."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields, replace
from typing import Any

logger = logging.getLogger(__name__)

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
    bedrock_model: str = "moonshotai.kimi-k2.5"
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
class ModelTierConfig:
    backend: str = ""   # "bedrock", "ollama", etc. Empty = use llm.backend
    model: str = ""     # Model ID. Empty = use llm.{backend}_model
    daily_budget: int = 0  # Max tokens/day. 0 = unlimited


@dataclass(frozen=True)
class RouterConfig:
    enabled: bool = False
    capable: ModelTierConfig = field(default_factory=ModelTierConfig)
    fast: ModelTierConfig = field(default_factory=ModelTierConfig)
    chat: ModelTierConfig = field(default_factory=ModelTierConfig)


@dataclass(frozen=True)
class RerankerConfig:
    backend: str = "local"  # "local", "bedrock", or registered provider name
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    candidates: int = 50  # widen RRF pool when reranking is on

    # Bedrock settings (Rerank API)
    bedrock_model: str = "cohere.rerank-v3-5:0"
    bedrock_region: str = "us-east-1"


@dataclass(frozen=True)
class LLMCapabilities:
    # --- Stable capabilities ---
    relationship_extract: bool = True
    rule_conflict_check: bool = True
    session_synthesis: bool = True
    consolidation: bool = True
    reranking: bool = False             # cross-encoder reranking (requires model download)
    knowledge_extraction: bool = False  # Neo4j graph extraction (requires Neo4j)
    search_v2: bool = False             # intent-routed search with token budgets

    # --- Experimental capabilities ---
    # These work but have unproven benefit/cost ratios or high resource demands.
    # Included in the 'enterprise' profile. May change behavior between releases.
    confidence_gating: bool = False     # EXPERIMENTAL: high reasoning demand per query
    type_routing: bool = False          # EXPERIMENTAL: query intent classification + type boost
    spreading_activation: bool = False  # EXPERIMENTAL: graph-based spreading activation retrieval
    mca_gate: bool = False              # EXPERIMENTAL: keyword coverage pre-filter (MCA)
    thought_extraction: str = "off"     # EXPERIMENTAL: extract entities from thinking sequences
                                        #   "off" = no extraction, "on_conclude" = extract on conclude,
                                        #   "on_every_thought" = extract on each add_thought()

    def active_list(self) -> list[str]:
        """Return names of enabled capabilities."""
        active = [
            name for name in (
                "relationship_extract", "rule_conflict_check",
                "session_synthesis", "consolidation",
                "reranking", "knowledge_extraction", "search_v2",
                "confidence_gating", "type_routing",
                "spreading_activation", "mca_gate",
            )
            if getattr(self, name)
        ]
        if self.thought_extraction != "off":
            active.append(f"thought_extraction:{self.thought_extraction}")
        return active


# Capabilities marked as experimental — may change behavior between releases.
EXPERIMENTAL_CAPABILITIES: frozenset[str] = frozenset({
    "confidence_gating", "type_routing",
    "spreading_activation", "mca_gate",
    "thought_extraction",
})


@dataclass(frozen=True)
class TerminalConfig:
    backend: str = "disabled"           # "native", "ttyd", "disabled"
    encryption_key: str | None = None   # Fernet key (native mode only)
    max_sessions: int = 5               # concurrent terminal sessions
    connect_timeout: int = 30           # SSH connect timeout (native mode)


@dataclass(frozen=True)
class WorkspaceConfig:
    default_backend: str = "opencode"     # which backend when not specified
    url: str = ""                         # OpenCode headless server URL (e.g. http://worker:8080)
    password: str = ""                    # OPENCODE_SERVER_PASSWORD on the worker
    default_agent: str = "cairn-build"    # Default agent for new sessions
    claude_code_enabled: bool = False     # Enable Claude Code backend
    claude_code_working_dir: str = ""     # cwd for claude subprocess
    claude_code_max_turns: int = 25       # --max-turns
    claude_code_max_budget: float = 10.0  # --max-budget-usd
    claude_code_mcp_url: str = ""         # Cairn MCP URL for self-service context
    claude_code_ssh_host: str = ""        # SSH host for remote execution (empty = local)
    claude_code_ssh_user: str = ""        # SSH user (empty = current user)
    claude_code_ssh_key: str = ""         # Path to SSH private key (empty = default)


@dataclass(frozen=True)
class BudgetConfig:
    rules: int = 3000           # Token budget for rules() responses
    search: int = 4000          # Token budget for search() responses
    recall: int = 8000          # Token budget for recall() responses
    cairn_stack: int = 3000     # Token budget for cairns(action='stack') responses
    insights: int = 4000        # Token budget for insights() responses
    workspace: int = 6000       # Token budget for workspace build_context()
    orient: int = 6000          # Token budget for orient() single-pass boot


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
class ClusteringConfig:
    min_cluster_size: int = 3       # Minimum members for a cluster
    min_samples: int = 2            # Core-point density (lower = more clusters)
    selection_method: str = "leaf"  # "eom" (fewer, larger) or "leaf" (finer-grained)
    staleness_hours: int = 24       # Recluster after this many hours
    staleness_growth_pct: int = 20  # Recluster after this % memory growth
    tsne_max_samples: int = 500     # t-SNE sample cap (O(n^2) memory)


@dataclass(frozen=True)
class Config:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    capabilities: LLMCapabilities = field(default_factory=LLMCapabilities)
    terminal: TerminalConfig = field(default_factory=TerminalConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    router: RouterConfig = field(default_factory=RouterConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    enrichment_enabled: bool = True
    profile: str = ""  # Active CAIRN_PROFILE name (empty = no profile)
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


# --- Editable keys whitelist ---
# Keys that can be changed via the UI and persisted in app_settings.
EDITABLE_KEYS: set[str] = {
    # LLM
    "llm.backend", "llm.bedrock_model", "llm.bedrock_region",
    "llm.ollama_url", "llm.ollama_model",
    "llm.gemini_model", "llm.gemini_api_key",
    "llm.openai_base_url", "llm.openai_model", "llm.openai_api_key",
    # Reranker
    "reranker.backend", "reranker.model", "reranker.candidates",
    "reranker.bedrock_model", "reranker.bedrock_region",
    # Router
    "router.enabled",
    "router.capable.backend", "router.capable.model", "router.capable.daily_budget",
    "router.fast.backend", "router.fast.model", "router.fast.daily_budget",
    "router.chat.backend", "router.chat.model", "router.chat.daily_budget",
    # Capabilities
    "capabilities.relationship_extract",
    "capabilities.rule_conflict_check", "capabilities.session_synthesis",
    "capabilities.consolidation", "capabilities.confidence_gating",
    "capabilities.reranking",
    "capabilities.type_routing", "capabilities.spreading_activation",
    "capabilities.mca_gate", "capabilities.knowledge_extraction",
    "capabilities.search_v2",
    "capabilities.thought_extraction",
    # Analytics
    "analytics.enabled", "analytics.retention_days",
    "analytics.cost_embedding_per_1k", "analytics.cost_llm_input_per_1k",
    "analytics.cost_llm_output_per_1k",
    # Auth
    "auth.enabled", "auth.api_key", "auth.header_name",
    # Terminal
    "terminal.backend", "terminal.max_sessions", "terminal.connect_timeout",
    # Neo4j
    "neo4j.uri", "neo4j.user", "neo4j.password", "neo4j.database",
    # Workspace
    "workspace.default_backend", "workspace.url", "workspace.password",
    "workspace.default_agent", "workspace.claude_code_enabled",
    "workspace.claude_code_working_dir", "workspace.claude_code_max_turns",
    "workspace.claude_code_max_budget", "workspace.claude_code_mcp_url",
    "workspace.claude_code_ssh_host", "workspace.claude_code_ssh_user", "workspace.claude_code_ssh_key",
    # Budget
    "budget.rules", "budget.search", "budget.recall",
    "budget.cairn_stack", "budget.insights", "budget.workspace",
    "budget.orient",
    # Clustering
    "clustering.min_cluster_size", "clustering.min_samples",
    "clustering.selection_method", "clustering.staleness_hours",
    "clustering.staleness_growth_pct", "clustering.tsne_max_samples",
    # Top-level
    "enrichment_enabled",
    "ingest_chunk_size", "ingest_chunk_overlap",
}

# Map of section -> dataclass for sub-configs that are editable
_SECTION_CLASSES = {
    "llm": LLMConfig,
    "reranker": RerankerConfig,
    "capabilities": LLMCapabilities,
    "analytics": AnalyticsConfig,
    "auth": AuthConfig,
    "terminal": TerminalConfig,
    "neo4j": Neo4jConfig,
    "workspace": WorkspaceConfig,
    "budget": BudgetConfig,
    "clustering": ClusteringConfig,
}

_BOOL_TRUTHY = {"true", "1", "yes"}

# --- Tiered profiles ---
# CAIRN_PROFILE sets capability defaults for common deployment patterns.
# Individual env vars always override profile defaults.
# Only env vars that DIFFER from hardcoded defaults need to be listed.
PROFILE_PRESETS: dict[str, dict[str, str]] = {
    # Vector-only: embedding + search, no LLM. Cheapest deployment.
    "vector": {
        "CAIRN_ENRICHMENT_ENABLED": "false",
        "CAIRN_LLM_RELATIONSHIP_EXTRACT": "false",
        "CAIRN_LLM_RULE_CONFLICT_CHECK": "false",
        "CAIRN_LLM_SESSION_SYNTHESIS": "false",
        "CAIRN_LLM_CONSOLIDATION": "false",
    },
    # LLM-enriched: summaries, relationships, synthesis. Matches current defaults.
    "enriched": {
        "CAIRN_ENRICHMENT_ENABLED": "true",
    },
    # Knowledge graph: enriched + Neo4j extraction + enhanced search pipeline.
    "knowledge": {
        "CAIRN_ENRICHMENT_ENABLED": "true",
        "CAIRN_KNOWLEDGE_EXTRACTION": "true",
        "CAIRN_SEARCH_V2": "true",
        "CAIRN_TYPE_ROUTING": "true",
        "CAIRN_RERANKING": "true",
    },
    # Enterprise: all features enabled, including experimental.
    "enterprise": {
        "CAIRN_ENRICHMENT_ENABLED": "true",
        "CAIRN_KNOWLEDGE_EXTRACTION": "true",
        "CAIRN_SEARCH_V2": "true",
        "CAIRN_TYPE_ROUTING": "true",
        "CAIRN_RERANKING": "true",
        "CAIRN_SPREADING_ACTIVATION": "true",
        "CAIRN_MCA_GATE": "true",
        "CAIRN_LLM_CONFIDENCE_GATING": "true",
        "CAIRN_ROUTER_ENABLED": "true",
    },
}


def _coerce(value: str, target_type: type) -> Any:
    """Coerce a string value to the target type."""
    if target_type is bool:
        return value.lower() in _BOOL_TRUTHY
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    # str, Optional[str]
    return value


def apply_overrides(config: Config, overrides: dict[str, str]) -> Config:
    """Rebuild a frozen Config by applying DB overrides.

    Only keys in EDITABLE_KEYS are applied; others are silently ignored.
    Supports up to 2-level nesting (e.g. router.capable.backend).
    """
    if not overrides:
        return config

    # Group overrides by section
    section_overrides: dict[str, dict[str, str]] = {}
    nested_overrides: dict[str, dict[str, dict[str, str]]] = {}
    top_overrides: dict[str, str] = {}

    for key, value in overrides.items():
        if key not in EDITABLE_KEYS:
            continue
        parts = key.split(".")
        if len(parts) == 3:
            # 2-level nested: router.capable.backend
            section, sub, field_name = parts
            nested_overrides.setdefault(section, {}).setdefault(sub, {})[field_name] = value
        elif len(parts) == 2:
            section, field_name = parts
            section_overrides.setdefault(section, {})[field_name] = value
        else:
            top_overrides[key] = value

    # Rebuild sub-configs
    replacements: dict[str, Any] = {}
    for section, field_overrides in section_overrides.items():
        if section not in _SECTION_CLASSES:
            continue
        sub_config = getattr(config, section)
        sub_replacements = {}
        for fname, fvalue in field_overrides.items():
            if not hasattr(sub_config, fname):
                continue
            current = getattr(sub_config, fname)
            target_type = type(current) if current is not None else str
            sub_replacements[fname] = _coerce(fvalue, target_type)
        if sub_replacements:
            replacements[section] = replace(sub_config, **sub_replacements)

    # Rebuild nested sub-configs (e.g. router.capable.backend)
    for section, sub_dict in nested_overrides.items():
        sub_config = replacements.get(section, getattr(config, section))
        sub_replacements = {}
        for sub_name, sub_fields in sub_dict.items():
            if not hasattr(sub_config, sub_name):
                continue
            tier = getattr(sub_config, sub_name)
            if not hasattr(tier, "__dataclass_fields__"):
                continue
            tier_replacements = {}
            for fname, fvalue in sub_fields.items():
                if not hasattr(tier, fname):
                    continue
                current = getattr(tier, fname)
                target_type = type(current) if current is not None else str
                tier_replacements[fname] = _coerce(fvalue, target_type)
            if tier_replacements:
                sub_replacements[sub_name] = replace(tier, **tier_replacements)
        if sub_replacements:
            replacements[section] = replace(sub_config, **sub_replacements)

    # Top-level fields
    for key, value in top_overrides.items():
        if not hasattr(config, key):
            continue
        current = getattr(config, key)
        target_type = type(current) if current is not None else str
        replacements[key] = _coerce(value, target_type)

    return replace(config, **replacements) if replacements else config


def config_to_flat(config: Config) -> dict[str, Any]:
    """Serialize config to a flat dict with dot-notation keys for the settings API."""
    result: dict[str, Any] = {}

    for f in fields(config):
        val = getattr(config, f.name)
        if hasattr(val, "__dataclass_fields__"):
            for sf in fields(val):
                sv = getattr(val, sf.name)
                if hasattr(sv, "__dataclass_fields__"):
                    # 2-level nesting (e.g. router.capable.backend)
                    for ssf in fields(sv):
                        result[f"{f.name}.{sf.name}.{ssf.name}"] = getattr(sv, ssf.name)
                else:
                    result[f"{f.name}.{sf.name}"] = sv
        else:
            # Skip list fields (cors_origins) — not useful in flat form
            if isinstance(val, list):
                continue
            result[f.name] = val

    return result


# Snapshot of env var values at load time, keyed by dot-notation config key.
# Used to determine source (default vs env vs db) for each setting.
_ENV_MAP: dict[str, str] = {
    "db.host": "CAIRN_DB_HOST", "db.port": "CAIRN_DB_PORT",
    "db.name": "CAIRN_DB_NAME", "db.user": "CAIRN_DB_USER",
    "db.password": "CAIRN_DB_PASS",
    "embedding.backend": "CAIRN_EMBEDDING_BACKEND",
    "embedding.model": "CAIRN_EMBEDDING_MODEL",
    "embedding.dimensions": "CAIRN_EMBEDDING_DIMENSIONS",
    "llm.backend": "CAIRN_LLM_BACKEND",
    "llm.bedrock_model": "CAIRN_BEDROCK_MODEL",
    "llm.bedrock_region": "AWS_DEFAULT_REGION",
    "llm.ollama_url": "CAIRN_OLLAMA_URL",
    "llm.ollama_model": "CAIRN_OLLAMA_MODEL",
    "llm.gemini_model": "CAIRN_GEMINI_MODEL",
    "llm.gemini_api_key": "CAIRN_GEMINI_API_KEY",
    "llm.openai_base_url": "CAIRN_OPENAI_BASE_URL",
    "llm.openai_model": "CAIRN_OPENAI_MODEL",
    "llm.openai_api_key": "CAIRN_OPENAI_API_KEY",
    "router.enabled": "CAIRN_ROUTER_ENABLED",
    "router.capable.backend": "CAIRN_ROUTER_CAPABLE_BACKEND",
    "router.capable.model": "CAIRN_ROUTER_CAPABLE_MODEL",
    "router.capable.daily_budget": "CAIRN_ROUTER_CAPABLE_BUDGET",
    "router.fast.backend": "CAIRN_ROUTER_FAST_BACKEND",
    "router.fast.model": "CAIRN_ROUTER_FAST_MODEL",
    "router.fast.daily_budget": "CAIRN_ROUTER_FAST_BUDGET",
    "router.chat.backend": "CAIRN_ROUTER_CHAT_BACKEND",
    "router.chat.model": "CAIRN_ROUTER_CHAT_MODEL",
    "router.chat.daily_budget": "CAIRN_ROUTER_CHAT_BUDGET",
    "neo4j.uri": "CAIRN_NEO4J_URI",
    "neo4j.user": "CAIRN_NEO4J_USER",
    "neo4j.password": "CAIRN_NEO4J_PASSWORD",
    "neo4j.database": "CAIRN_NEO4J_DATABASE",
    "reranker.backend": "CAIRN_RERANKER_BACKEND",
    "reranker.model": "CAIRN_RERANKER_MODEL",
    "reranker.candidates": "CAIRN_RERANK_CANDIDATES",
    "capabilities.relationship_extract": "CAIRN_LLM_RELATIONSHIP_EXTRACT",
    "capabilities.rule_conflict_check": "CAIRN_LLM_RULE_CONFLICT_CHECK",
    "capabilities.session_synthesis": "CAIRN_LLM_SESSION_SYNTHESIS",
    "capabilities.consolidation": "CAIRN_LLM_CONSOLIDATION",
    "capabilities.confidence_gating": "CAIRN_LLM_CONFIDENCE_GATING",
    "capabilities.reranking": "CAIRN_RERANKING",
    "capabilities.type_routing": "CAIRN_TYPE_ROUTING",
    "capabilities.spreading_activation": "CAIRN_SPREADING_ACTIVATION",
    "capabilities.mca_gate": "CAIRN_MCA_GATE",
    "capabilities.knowledge_extraction": "CAIRN_KNOWLEDGE_EXTRACTION",
    "capabilities.search_v2": "CAIRN_SEARCH_V2",
    "capabilities.thought_extraction": "CAIRN_THOUGHT_EXTRACTION",
    "terminal.backend": "CAIRN_TERMINAL_BACKEND",
    "terminal.max_sessions": "CAIRN_TERMINAL_MAX_SESSIONS",
    "terminal.connect_timeout": "CAIRN_TERMINAL_CONNECT_TIMEOUT",
    "auth.enabled": "CAIRN_AUTH_ENABLED",
    "auth.api_key": "CAIRN_API_KEY",
    "auth.header_name": "CAIRN_AUTH_HEADER",
    "analytics.enabled": "CAIRN_ANALYTICS_ENABLED",
    "analytics.retention_days": "CAIRN_ANALYTICS_RETENTION_DAYS",
    "analytics.cost_embedding_per_1k": "CAIRN_ANALYTICS_COST_EMBEDDING",
    "analytics.cost_llm_input_per_1k": "CAIRN_ANALYTICS_COST_LLM_INPUT",
    "analytics.cost_llm_output_per_1k": "CAIRN_ANALYTICS_COST_LLM_OUTPUT",
    "workspace.default_backend": "CAIRN_WORKSPACE_BACKEND",
    "workspace.url": "CAIRN_OPENCODE_URL",
    "workspace.password": "CAIRN_OPENCODE_PASSWORD",
    "workspace.default_agent": "CAIRN_OPENCODE_DEFAULT_AGENT",
    "workspace.claude_code_enabled": "CAIRN_CLAUDE_CODE_ENABLED",
    "workspace.claude_code_working_dir": "CAIRN_CLAUDE_CODE_WORKING_DIR",
    "workspace.claude_code_max_turns": "CAIRN_CLAUDE_CODE_MAX_TURNS",
    "workspace.claude_code_max_budget": "CAIRN_CLAUDE_CODE_MAX_BUDGET",
    "workspace.claude_code_mcp_url": "CAIRN_CLAUDE_CODE_MCP_URL",
    "workspace.claude_code_ssh_host": "CAIRN_CLAUDE_CODE_SSH_HOST",
    "workspace.claude_code_ssh_user": "CAIRN_CLAUDE_CODE_SSH_USER",
    "workspace.claude_code_ssh_key": "CAIRN_CLAUDE_CODE_SSH_KEY",
    "budget.rules": "CAIRN_BUDGET_RULES",
    "budget.search": "CAIRN_BUDGET_SEARCH",
    "budget.recall": "CAIRN_BUDGET_RECALL",
    "budget.cairn_stack": "CAIRN_BUDGET_CAIRN_STACK",
    "budget.insights": "CAIRN_BUDGET_INSIGHTS",
    "budget.workspace": "CAIRN_BUDGET_WORKSPACE",
    "budget.orient": "CAIRN_BUDGET_ORIENT",
    "clustering.min_cluster_size": "CAIRN_CLUSTER_MIN_SIZE",
    "clustering.min_samples": "CAIRN_CLUSTER_MIN_SAMPLES",
    "clustering.selection_method": "CAIRN_CLUSTER_SELECTION_METHOD",
    "clustering.staleness_hours": "CAIRN_CLUSTER_STALENESS_HOURS",
    "clustering.staleness_growth_pct": "CAIRN_CLUSTER_STALENESS_GROWTH_PCT",
    "clustering.tsne_max_samples": "CAIRN_CLUSTER_TSNE_MAX_SAMPLES",
    "enrichment_enabled": "CAIRN_ENRICHMENT_ENABLED",
    "profile": "CAIRN_PROFILE",
    "transport": "CAIRN_TRANSPORT",
    "http_host": "CAIRN_HTTP_HOST",
    "http_port": "CAIRN_HTTP_PORT",
    "ingest_chunk_size": "CAIRN_INGEST_CHUNK_SIZE",
    "ingest_chunk_overlap": "CAIRN_INGEST_CHUNK_OVERLAP",
}


def env_values() -> dict[str, str | None]:
    """Snapshot current env var values for source detection."""
    return {key: os.getenv(env_var) for key, env_var in _ENV_MAP.items()}


def load_config() -> Config:
    """Load configuration from environment variables.

    If CAIRN_PROFILE is set, profile defaults are injected via
    os.environ.setdefault() — individual env vars always win.
    """
    # --- Profile resolution (must run before any os.getenv reads) ---
    profile_name = os.getenv("CAIRN_PROFILE", "").lower().strip()
    if profile_name:
        preset = PROFILE_PRESETS.get(profile_name)
        if preset:
            for var, val in preset.items():
                os.environ.setdefault(var, val)
            logger.info("Profile applied: %s (%d defaults)", profile_name, len(preset))
        else:
            logger.warning(
                "Unknown CAIRN_PROFILE '%s' (valid: %s)",
                profile_name, ", ".join(sorted(PROFILE_PRESETS)),
            )
            profile_name = ""

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
            bedrock_model=os.getenv("CAIRN_BEDROCK_MODEL", "moonshotai.kimi-k2.5"),
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
            relationship_extract=os.getenv("CAIRN_LLM_RELATIONSHIP_EXTRACT", "true").lower() in ("true", "1", "yes"),
            rule_conflict_check=os.getenv("CAIRN_LLM_RULE_CONFLICT_CHECK", "true").lower() in ("true", "1", "yes"),
            session_synthesis=os.getenv("CAIRN_LLM_SESSION_SYNTHESIS", "true").lower() in ("true", "1", "yes"),
            consolidation=os.getenv("CAIRN_LLM_CONSOLIDATION", "true").lower() in ("true", "1", "yes"),
            confidence_gating=os.getenv("CAIRN_LLM_CONFIDENCE_GATING", "false").lower() in ("true", "1", "yes"),
            reranking=os.getenv("CAIRN_RERANKING", "false").lower() in ("true", "1", "yes"),
            type_routing=os.getenv("CAIRN_TYPE_ROUTING", "false").lower() in ("true", "1", "yes"),
            spreading_activation=os.getenv("CAIRN_SPREADING_ACTIVATION", "false").lower() in ("true", "1", "yes"),
            mca_gate=os.getenv("CAIRN_MCA_GATE", "false").lower() in ("true", "1", "yes"),
            knowledge_extraction=os.getenv("CAIRN_KNOWLEDGE_EXTRACTION", "false").lower() in ("true", "1", "yes"),
            search_v2=os.getenv("CAIRN_SEARCH_V2", "false").lower() in ("true", "1", "yes"),
            thought_extraction=os.getenv("CAIRN_THOUGHT_EXTRACTION", "off").lower().strip(),
        ),
        terminal=TerminalConfig(
            backend=os.getenv("CAIRN_TERMINAL_BACKEND", "disabled"),
            encryption_key=os.getenv("CAIRN_SSH_ENCRYPTION_KEY") or None,
            max_sessions=int(os.getenv("CAIRN_TERMINAL_MAX_SESSIONS", "5")),
            connect_timeout=int(os.getenv("CAIRN_TERMINAL_CONNECT_TIMEOUT", "30")),
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
        router=RouterConfig(
            enabled=os.getenv("CAIRN_ROUTER_ENABLED", "false").lower() in ("true", "1", "yes"),
            capable=ModelTierConfig(
                backend=os.getenv("CAIRN_ROUTER_CAPABLE_BACKEND", ""),
                model=os.getenv("CAIRN_ROUTER_CAPABLE_MODEL", ""),
                daily_budget=int(os.getenv("CAIRN_ROUTER_CAPABLE_BUDGET", "0")),
            ),
            fast=ModelTierConfig(
                backend=os.getenv("CAIRN_ROUTER_FAST_BACKEND", ""),
                model=os.getenv("CAIRN_ROUTER_FAST_MODEL", ""),
                daily_budget=int(os.getenv("CAIRN_ROUTER_FAST_BUDGET", "0")),
            ),
            chat=ModelTierConfig(
                backend=os.getenv("CAIRN_ROUTER_CHAT_BACKEND", ""),
                model=os.getenv("CAIRN_ROUTER_CHAT_MODEL", ""),
                daily_budget=int(os.getenv("CAIRN_ROUTER_CHAT_BUDGET", "0")),
            ),
        ),
        reranker=RerankerConfig(
            backend=os.getenv("CAIRN_RERANKER_BACKEND", "local"),
            model=os.getenv("CAIRN_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
            candidates=int(os.getenv("CAIRN_RERANK_CANDIDATES", "50")),
            bedrock_model=os.getenv("CAIRN_RERANKER_BEDROCK_MODEL", "amazon.rerank-v1:0"),
            bedrock_region=os.getenv("CAIRN_RERANKER_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
        ),
        workspace=WorkspaceConfig(
            default_backend=os.getenv("CAIRN_WORKSPACE_BACKEND", "opencode"),
            url=os.getenv("CAIRN_OPENCODE_URL", ""),
            password=os.getenv("CAIRN_OPENCODE_PASSWORD", ""),
            default_agent=os.getenv("CAIRN_OPENCODE_DEFAULT_AGENT", "cairn-build"),
            claude_code_enabled=os.getenv("CAIRN_CLAUDE_CODE_ENABLED", "false").lower() in ("true", "1", "yes"),
            claude_code_working_dir=os.getenv("CAIRN_CLAUDE_CODE_WORKING_DIR", ""),
            claude_code_max_turns=int(os.getenv("CAIRN_CLAUDE_CODE_MAX_TURNS", "25")),
            claude_code_max_budget=float(os.getenv("CAIRN_CLAUDE_CODE_MAX_BUDGET", "10.0")),
            claude_code_mcp_url=os.getenv("CAIRN_CLAUDE_CODE_MCP_URL", ""),
            claude_code_ssh_host=os.getenv("CAIRN_CLAUDE_CODE_SSH_HOST", ""),
            claude_code_ssh_user=os.getenv("CAIRN_CLAUDE_CODE_SSH_USER", ""),
            claude_code_ssh_key=os.getenv("CAIRN_CLAUDE_CODE_SSH_KEY", ""),
        ),
        budget=BudgetConfig(
            rules=int(os.getenv("CAIRN_BUDGET_RULES", "3000")),
            search=int(os.getenv("CAIRN_BUDGET_SEARCH", "4000")),
            recall=int(os.getenv("CAIRN_BUDGET_RECALL", "8000")),
            cairn_stack=int(os.getenv("CAIRN_BUDGET_CAIRN_STACK", "3000")),
            insights=int(os.getenv("CAIRN_BUDGET_INSIGHTS", "4000")),
            workspace=int(os.getenv("CAIRN_BUDGET_WORKSPACE", "6000")),
        orient=int(os.getenv("CAIRN_BUDGET_ORIENT", "6000")),
        ),
        clustering=ClusteringConfig(
            min_cluster_size=int(os.getenv("CAIRN_CLUSTER_MIN_SIZE", "3")),
            min_samples=int(os.getenv("CAIRN_CLUSTER_MIN_SAMPLES", "2")),
            selection_method=os.getenv("CAIRN_CLUSTER_SELECTION_METHOD", "leaf"),
            staleness_hours=int(os.getenv("CAIRN_CLUSTER_STALENESS_HOURS", "24")),
            staleness_growth_pct=int(os.getenv("CAIRN_CLUSTER_STALENESS_GROWTH_PCT", "20")),
            tsne_max_samples=int(os.getenv("CAIRN_CLUSTER_TSNE_MAX_SAMPLES", "500")),
        ),
        enrichment_enabled=os.getenv("CAIRN_ENRICHMENT_ENABLED", "true").lower() in ("true", "1", "yes"),
        profile=profile_name,
        transport=os.getenv("CAIRN_TRANSPORT", "stdio"),
        http_host=os.getenv("CAIRN_HTTP_HOST", "0.0.0.0"),
        http_port=int(os.getenv("CAIRN_HTTP_PORT", "8000")),
        cors_origins=_parse_cors_origins(os.getenv("CAIRN_CORS_ORIGINS", "*")),
        event_archive_dir=os.getenv("CAIRN_EVENT_ARCHIVE_DIR") or None,
        ingest_chunk_size=int(os.getenv("CAIRN_INGEST_CHUNK_SIZE", "512")),
        ingest_chunk_overlap=int(os.getenv("CAIRN_INGEST_CHUNK_OVERLAP", "64")),
    )
