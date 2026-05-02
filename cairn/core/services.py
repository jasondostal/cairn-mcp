"""Service container and factory. Centralizes component initialization.

Post-cut (v0.80.0): memory core only. Agent infrastructure removed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cairn.config import Config, load_config
from cairn.core.activation import ActivationEngine
from cairn.core.analytics import (
    AnalyticsQueryEngine,
    RollupWorker,
    UsageTracker,
    init_analytics_tracker,
)
from cairn.core.clustering import ClusterEngine
from cairn.core.consolidation import ConsolidationEngine
from cairn.core.drift import DriftDetector
from cairn.core.enrichment import Enricher
from cairn.core.event_bus import EventBus
from cairn.core.event_dispatcher import EventDispatcher
from cairn.core.extraction import KnowledgeExtractor
from cairn.core.ingest import IngestPipeline
from cairn.core.memory import MemoryStore
from cairn.core.projects import ProjectManager
from cairn.core.reranker import get_reranker
from cairn.core.search import SearchEngine
from cairn.core.search_v2 import SearchV2
from cairn.core.stats import (
    init_embedding_stats,
    init_event_bus_ref,
    init_event_bus_stats,
    init_llm_stats,
)
from cairn.core.thinking import ThinkingEngine
from cairn.core.user import UserManager
from cairn.core.work_items import WorkItemManager
from cairn.core.working_memory import WorkingMemoryStore
from cairn.embedding import get_embedding_engine
from cairn.embedding.interface import EmbeddingInterface
from cairn.graph import get_graph_provider
from cairn.graph.interface import GraphProvider
from cairn.llm import get_llm
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.core.beliefs import BeliefStore
    from cairn.core.consolidation import ConsolidationWorker
    from cairn.core.decay import DecayWorker
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)


@dataclass
class Services:
    """Holds all initialized Cairn components (memory core)."""

    config: Config
    db: Database
    embedding: EmbeddingInterface
    llm: LLMInterface | None
    enricher: Enricher | None
    graph_provider: GraphProvider
    knowledge_extractor: KnowledgeExtractor | None
    memory_store: MemoryStore
    search_engine: SearchV2  # unified search — wraps SearchEngine
    cluster_engine: ClusterEngine
    project_manager: ProjectManager
    thinking_engine: ThinkingEngine
    consolidation_engine: ConsolidationEngine
    event_bus: EventBus
    drift_detector: DriftDetector
    ingest_pipeline: IngestPipeline
    work_item_manager: WorkItemManager  # experimental — tagged, not deleted
    event_dispatcher: EventDispatcher | None
    analytics_tracker: UsageTracker | None
    rollup_worker: RollupWorker | None
    decay_worker: DecayWorker | None
    analytics_engine: AnalyticsQueryEngine | None
    user_manager: UserManager | None
    working_memory_store: WorkingMemoryStore
    belief_store: BeliefStore | None
    consolidation_worker: ConsolidationWorker | None


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

    # Analytics — optional, for UI dashboard
    analytics_tracker = None
    rollup_worker = None
    decay_worker = None
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
    llm: LLMInterface | None = None
    llm_capable: LLMInterface | None = None
    llm_fast: LLMInterface | None = None
    llm_chat: LLMInterface | None = None
    enricher: Enricher | None = None
    if config.enrichment_enabled:
        try:
            if config.router.enabled:
                from cairn.llm.router import ModelRouter
                router = ModelRouter(config.router, config.llm)
                llm_capable = router.for_operation("capable")
                llm_fast = router.for_operation("fast")
                llm_chat = router.for_operation("chat")
                llm = llm_chat
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

    # Graph provider (required — Neo4j must be available)
    graph_provider = get_graph_provider(config.neo4j)
    logger.info("Neo4j graph provider initialized")

    knowledge_extractor = None
    if capabilities.knowledge_extraction and llm_capable:
        knowledge_extractor = KnowledgeExtractor(llm_capable, embedding, graph_provider)
        logger.info("Knowledge extraction enabled")
    elif capabilities.knowledge_extraction and not llm:
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
        event_bus=None,  # set after event_bus creation below
    )
    project_manager = ProjectManager(db)

    # Event bus — created early so managers can publish events
    event_bus = EventBus(db, project_manager)

    # Wire event_bus into memory_store
    memory_store.event_bus = event_bus

    # Register memory enrichment listener (async graph persist + relationships)
    from cairn.listeners.memory_enrichment import MemoryEnrichmentListener
    _memory_listener = MemoryEnrichmentListener(memory_store)
    _memory_listener.register(event_bus)
    logger.info("MemoryEnrichmentListener registered with EventBus")

    # Register graph projection listener
    from cairn.listeners.graph_projection import GraphProjectionListener
    _graph_listener = GraphProjectionListener(graph_provider, db)
    _graph_listener.register(event_bus)
    logger.info("GraphProjectionListener registered with EventBus")

    # Register memory access tracking listener (bumps access_count on search/recall)
    from cairn.listeners.memory_access import MemoryAccessListener
    _access_listener = MemoryAccessListener(db)
    _access_listener.register(event_bus)
    logger.info("MemoryAccessListener registered with EventBus")

    # Register code index listener for event-driven re-indexing
    if capabilities.code_intelligence:
        from cairn.listeners.code_index_listener import CodeIndexListener
        _code_listener = CodeIndexListener(graph_provider, db)
        _code_listener.register(event_bus)
        logger.info("CodeIndexListener registered with EventBus")

    # Work item manager — experimental, tagged for UI observability
    _wi_mgr = WorkItemManager(
        db, embedding, graph=graph_provider,
        knowledge_extractor=knowledge_extractor,
        event_bus=event_bus,
    )

    # User manager — created when auth is enabled with JWT
    _user_manager = None
    if config.auth.enabled and config.auth.jwt_secret:
        _user_manager = UserManager(db)
        logger.info("UserManager initialized (JWT auth enabled)")

    # Event dispatcher — background delivery worker
    event_dispatcher = EventDispatcher(db, event_bus)

    # RRF search engine (core signal fusion)
    rrf_engine = SearchEngine(
        db, embedding, llm=llm_fast, capabilities=capabilities,
        reranker=reranker, rerank_candidates=config.reranker.candidates,
        activation_engine=activation_engine,
        graph_provider=graph_provider,
        decay_lambda=config.decay_lambda,
        memory_store=memory_store,
    )

    # Unified search — always wraps SearchEngine
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

    # Decay worker (controlled forgetting — background thread)
    if config.decay.enabled:
        from cairn.core.decay import DecayWorker
        decay_worker = DecayWorker(db, config.decay, decay_lambda=config.decay_lambda)
        logger.info("DecayWorker enabled (dry_run=%s)", config.decay.dry_run)

    # Belief store
    from cairn.core.beliefs import BeliefStore
    _belief_store = BeliefStore(db, event_bus=event_bus)

    # Cluster engine (needed by both insights and consolidation worker)
    _cluster_engine = ClusterEngine(db, embedding, llm=llm_fast, config=config.clustering)

    # Consolidation worker (background thread for memory synthesis)
    _consolidation_worker = None
    if config.consolidation_worker.enabled:
        from cairn.core.consolidation import ConsolidationWorker
        _consolidation_engine = ConsolidationEngine(db, embedding, llm=llm_fast, capabilities=capabilities)
        _consolidation_worker = ConsolidationWorker(
            engine=_consolidation_engine,
            db=db,
            config=config.consolidation_worker,
            cluster_engine=_cluster_engine,
            memory_store=memory_store,
            event_bus=event_bus,
        )
        logger.info("ConsolidationWorker enabled (dry_run=%s)", config.consolidation_worker.dry_run)

    # Wire EventBus ref into stats module
    init_event_bus_ref(event_bus)

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
        cluster_engine=_cluster_engine,
        project_manager=project_manager,
        work_item_manager=_wi_mgr,
        thinking_engine=ThinkingEngine(
            db,
            graph=graph_provider,
            knowledge_extractor=knowledge_extractor,
            embedding=embedding,
            thought_extraction=capabilities.thought_extraction,
            event_bus=event_bus,
        ),
        consolidation_engine=ConsolidationEngine(db, embedding, llm=llm_fast, capabilities=capabilities),
        event_bus=event_bus,
        event_dispatcher=event_dispatcher,
        drift_detector=DriftDetector(db),
        ingest_pipeline=IngestPipeline(db, project_manager, memory_store, llm_fast, config),
        analytics_tracker=analytics_tracker,
        rollup_worker=rollup_worker,
        decay_worker=decay_worker,
        analytics_engine=analytics_engine,
        user_manager=_user_manager,
        working_memory_store=WorkingMemoryStore(
            db, embedding=embedding, event_bus=event_bus,
            memory_store=memory_store, belief_store=_belief_store,
        ),
        belief_store=_belief_store,
        consolidation_worker=_consolidation_worker,
    )
