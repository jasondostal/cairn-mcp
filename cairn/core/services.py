"""Service container and factory. Centralizes component initialization."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cairn.config import Config, LLMCapabilities, load_config
from cairn.core.analytics import AnalyticsQueryEngine, RollupWorker, UsageTracker, init_analytics_tracker
# CairnManager removed in v0.37.0 — trail() + temporal graph queries replace cairns
from cairn.core.clustering import ClusterEngine
from cairn.core.conversations import ConversationManager
from cairn.core.consolidation import ConsolidationEngine
from cairn.core.event_bus import EventBus
from cairn.core.event_dispatcher import EventDispatcher
from cairn.core.drift import DriftDetector
from cairn.core.enrichment import Enricher
from cairn.core.extraction import KnowledgeExtractor
from cairn.core.ingest import IngestPipeline
from cairn.core.activation import ActivationEngine
from cairn.core.memory import MemoryStore
from cairn.core.messages import MessageManager
from cairn.core.terminal import TerminalHostManager
from cairn.core.workspace import WorkspaceManager
from cairn.integrations.interface import WorkspaceBackend
from cairn.integrations.opencode import OpenCodeClient, OpenCodeBackend
from cairn.core.projects import ProjectManager
from cairn.core.reranker import get_reranker
from cairn.core.reranker.interface import RerankerInterface
from cairn.core.search import SearchEngine
from cairn.core.search_v2 import SearchV2
from cairn.core.synthesis import SessionSynthesizer
from cairn.core.tasks import TaskManager
from cairn.core.thinking import ThinkingEngine
from cairn.core.work_items import WorkItemManager
from cairn.core.stats import init_embedding_stats, init_event_bus_stats, init_llm_stats
from cairn.embedding import get_embedding_engine
from cairn.embedding.interface import EmbeddingInterface
from cairn.graph import get_graph_provider
from cairn.graph.interface import GraphProvider
from cairn.llm import get_llm
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)


@dataclass
class Services:
    """Holds all initialized Cairn components."""

    config: Config
    db: Database
    embedding: EmbeddingInterface
    llm: LLMInterface | None
    enricher: Enricher | None
    graph_provider: GraphProvider | None
    knowledge_extractor: KnowledgeExtractor | None
    memory_store: MemoryStore
    search_engine: SearchV2  # unified search — wraps SearchEngine
    cluster_engine: ClusterEngine
    project_manager: ProjectManager
    task_manager: TaskManager
    thinking_engine: ThinkingEngine
    session_synthesizer: SessionSynthesizer
    consolidation_engine: ConsolidationEngine
    cairn_manager: object  # deprecated — kept as None for backward compat
    event_bus: EventBus
    drift_detector: DriftDetector
    message_manager: MessageManager
    ingest_pipeline: IngestPipeline
    terminal_host_manager: TerminalHostManager | None
    opencode: OpenCodeClient | None  # deprecated — use workspace_backends
    workspace_backends: dict[str, WorkspaceBackend]
    workspace_manager: WorkspaceManager
    work_item_manager: WorkItemManager
    conversation_manager: ConversationManager
    event_dispatcher: EventDispatcher | None
    analytics_tracker: UsageTracker | None
    rollup_worker: RollupWorker | None
    analytics_engine: AnalyticsQueryEngine | None


def create_services(config: Config | None = None, db: Database | None = None) -> Services:
    """Build all Cairn services from config.

    Args:
        config: Configuration to use. Loads from env if None.
        db: Pre-connected database. Creates new one if None.
    """
    if config is None:
        config = load_config()

    if db is None:
        db = Database(config.db)

    # Analytics first — so the tracker singleton is available when backends emit events
    analytics_tracker = None
    rollup_worker = None
    analytics_engine = None
    if config.analytics.enabled:
        analytics_tracker = UsageTracker(db)
        init_analytics_tracker(analytics_tracker)
        rollup_worker = RollupWorker(db, retention_days=config.analytics.retention_days)
        analytics_engine = AnalyticsQueryEngine(db, analytics_config=config.analytics)
        logger.info("Analytics enabled (retention=%dd)", config.analytics.retention_days)

    embedding = get_embedding_engine(config.embedding)

    # Initialize embedding stats
    if config.embedding.backend == "bedrock":
        emb_model = config.embedding.bedrock_model
    elif config.embedding.backend == "openai":
        emb_model = config.embedding.openai_model
    else:
        emb_model = config.embedding.model
    init_embedding_stats(config.embedding.backend, emb_model)
    init_event_bus_stats()

    # LLM enrichment (optional, graceful if disabled)
    llm = None
    llm_capable = None
    llm_fast = None
    llm_chat = None
    enricher = None
    if config.enrichment_enabled:
        try:
            if config.router.enabled:
                from cairn.llm.router import ModelRouter
                router = ModelRouter(config.router, config.llm)
                llm_capable = router.for_operation("capable")
                llm_fast = router.for_operation("fast")
                llm_chat = router.for_operation("chat")
                llm = llm_chat  # default for components that don't have a tier assignment
                init_llm_stats(config.llm.backend, router.get_model_name())
                enricher = Enricher(llm_fast)
                logger.info("Model router enabled: capable=%s, fast=%s, chat=%s",
                            llm_capable.get_model_name(), llm_fast.get_model_name(), llm_chat.get_model_name())
            else:
                llm = get_llm(config.llm)
                llm_capable = llm
                llm_fast = llm
                llm_chat = llm
                init_llm_stats(config.llm.backend, llm.get_model_name())
                enricher = Enricher(llm)
                logger.info("Enrichment enabled: %s", config.llm.backend)
        except Exception:
            logger.warning("Failed to initialize LLM, enrichment disabled", exc_info=True)
    else:
        logger.info("Enrichment disabled by config")

    capabilities = config.capabilities

    # Graph provider (optional, for knowledge extraction)
    graph_provider = None
    knowledge_extractor = None
    if capabilities.knowledge_extraction:
        graph_provider = get_graph_provider(config.neo4j)
        if graph_provider and llm_capable:
            knowledge_extractor = KnowledgeExtractor(llm_capable, embedding, graph_provider)
            logger.info("Knowledge extraction enabled (Neo4j graph)")
        elif not graph_provider:
            logger.warning("Knowledge extraction requested but Neo4j not available (set CAIRN_GRAPH_BACKEND=neo4j)")
        elif not llm:
            logger.warning("Knowledge extraction requested but LLM not available")

    # Reranker (optional, lazy-loaded on first query)
    reranker = None
    if capabilities.reranking:
        try:
            reranker = get_reranker(config.reranker)
            logger.info("Reranking enabled: %s", config.reranker.backend)
        except Exception:
            logger.warning("Failed to create reranker, reranking disabled", exc_info=True)

    # Activation engine (optional, for spreading activation)
    activation_engine = None
    if capabilities.spreading_activation:
        activation_engine = ActivationEngine(db)
        logger.info("Spreading activation enabled")

    memory_store = MemoryStore(
        db, embedding, enricher=enricher, llm=llm_capable, capabilities=capabilities,
        knowledge_extractor=knowledge_extractor,
    )
    project_manager = ProjectManager(db)

    # Event bus — created early so managers can publish events
    event_bus = EventBus(db, project_manager)

    # Register graph projection listener if graph is available
    if graph_provider:
        from cairn.listeners.graph_projection import GraphProjectionListener
        _graph_listener = GraphProjectionListener(graph_provider, db)
        _graph_listener.register(event_bus)
        logger.info("GraphProjectionListener registered with EventBus")

    # Event dispatcher — background delivery worker (started in _start_workers)
    event_dispatcher = EventDispatcher(db, event_bus)

    # RRF search engine (core signal fusion)
    rrf_engine = SearchEngine(
        db, embedding, llm=llm_fast, capabilities=capabilities,
        reranker=reranker, rerank_candidates=config.reranker.candidates,
        activation_engine=activation_engine,
        graph_provider=graph_provider,
    )

    # Unified search — always wraps SearchEngine
    # Passthrough when search_v2 capability is off, enhanced pipeline when on
    unified_search = SearchV2(
        db=db,
        embedding=embedding,
        graph=graph_provider,
        llm=llm_fast,
        capabilities=capabilities,
        reranker=reranker,
        rerank_candidates=config.reranker.candidates,
        fallback_engine=rrf_engine,
    )
    if capabilities.search_v2:
        logger.info("Search: enhanced mode (intent routing + token budgets)")
    else:
        logger.info("Search: standard mode (RRF hybrid)")

    # Terminal host manager (optional, based on config)
    terminal_host_manager = None
    if config.terminal.backend != "disabled":
        if config.terminal.backend == "native" and not config.terminal.encryption_key:
            logger.warning("Terminal backend=native but no encryption key — terminal disabled")
        else:
            terminal_host_manager = TerminalHostManager(db, config.terminal)
            logger.info("Terminal enabled: backend=%s", config.terminal.backend)

    # Workspace backends (optional, for workspace feature)
    opencode = None
    workspace_backends: dict[str, WorkspaceBackend] = {}

    if config.workspace.url:
        opencode = OpenCodeClient(
            url=config.workspace.url,
            password=config.workspace.password,
        )
        workspace_backends["opencode"] = OpenCodeBackend(opencode)
        logger.info("OpenCode workspace backend enabled: %s", config.workspace.url)

    if config.workspace.claude_code_enabled:
        from cairn.integrations.claude_code import ClaudeCodeBackend, ClaudeCodeConfig
        cc_config = ClaudeCodeConfig(
            working_dir=config.workspace.claude_code_working_dir,
            max_turns=config.workspace.claude_code_max_turns,
            max_budget_usd=config.workspace.claude_code_max_budget,
            cairn_mcp_url=config.workspace.claude_code_mcp_url,
        )
        workspace_backends["claude_code"] = ClaudeCodeBackend(cc_config)
        logger.info("Claude Code workspace backend enabled")

    return Services(
        config=config,
        db=db,
        embedding=embedding,
        llm=llm_chat,
        enricher=enricher,
        graph_provider=graph_provider,
        knowledge_extractor=knowledge_extractor,
        memory_store=memory_store,
        search_engine=unified_search,
        cluster_engine=ClusterEngine(db, embedding, llm=llm_fast),
        project_manager=project_manager,
        task_manager=TaskManager(db, graph=graph_provider, event_bus=event_bus),
        work_item_manager=(_wi_mgr := WorkItemManager(
            db, embedding, graph=graph_provider,
            knowledge_extractor=knowledge_extractor,
            event_bus=event_bus,
        )),
        thinking_engine=ThinkingEngine(
            db,
            graph=graph_provider,
            knowledge_extractor=knowledge_extractor,
            embedding=embedding,
            thought_extraction=capabilities.thought_extraction,
            event_bus=event_bus,
        ),
        session_synthesizer=SessionSynthesizer(db, llm=llm_fast, capabilities=capabilities),
        consolidation_engine=ConsolidationEngine(db, embedding, llm=llm_fast, capabilities=capabilities),
        cairn_manager=None,  # removed in v0.37.0
        event_bus=event_bus,
        event_dispatcher=event_dispatcher,
        drift_detector=DriftDetector(db),
        message_manager=(_msg_mgr := MessageManager(db)),
        ingest_pipeline=IngestPipeline(db, project_manager, memory_store, llm_fast, config),
        terminal_host_manager=terminal_host_manager,
        opencode=opencode,
        workspace_backends=workspace_backends,
        workspace_manager=WorkspaceManager(
            db, workspace_backends,
            default_backend=config.workspace.default_backend,
            message_manager=_msg_mgr,
            work_item_manager=_wi_mgr,
            default_agent=config.workspace.default_agent,
            budget_tokens=config.budget.workspace,
        ),
        conversation_manager=ConversationManager(db, llm=llm_fast),
        analytics_tracker=analytics_tracker,
        rollup_worker=rollup_worker,
        analytics_engine=analytics_engine,
    )
