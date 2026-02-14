"""Service container and factory. Centralizes component initialization."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cairn.config import Config, LLMCapabilities, load_config
from cairn.core.analytics import AnalyticsQueryEngine, RollupWorker, UsageTracker, init_analytics_tracker
from cairn.core.cairns import CairnManager
from cairn.core.clustering import ClusterEngine
from cairn.core.digest import DigestWorker
from cairn.core.consolidation import ConsolidationEngine
from cairn.core.drift import DriftDetector
from cairn.core.enrichment import Enricher
from cairn.core.extraction import KnowledgeExtractor
from cairn.core.ingest import IngestPipeline
from cairn.core.activation import ActivationEngine
from cairn.core.memory import MemoryStore
from cairn.core.messages import MessageManager
from cairn.core.terminal import TerminalHostManager
from cairn.core.projects import ProjectManager
from cairn.core.reranker import get_reranker
from cairn.core.reranker.interface import RerankerInterface
from cairn.core.search import SearchEngine
from cairn.core.search_v2 import SearchV2
from cairn.core.synthesis import SessionSynthesizer
from cairn.core.tasks import TaskManager
from cairn.core.thinking import ThinkingEngine
from cairn.core.stats import init_embedding_stats, init_llm_stats, init_digest_stats
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
    search_engine: SearchEngine
    search_v2: SearchV2 | None
    cluster_engine: ClusterEngine
    project_manager: ProjectManager
    task_manager: TaskManager
    thinking_engine: ThinkingEngine
    session_synthesizer: SessionSynthesizer
    consolidation_engine: ConsolidationEngine
    cairn_manager: CairnManager
    digest_worker: DigestWorker
    drift_detector: DriftDetector
    message_manager: MessageManager
    ingest_pipeline: IngestPipeline
    terminal_host_manager: TerminalHostManager | None
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

    # LLM enrichment (optional, graceful if disabled)
    llm = None
    enricher = None
    if config.enrichment_enabled:
        try:
            llm = get_llm(config.llm)
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
        if graph_provider and llm:
            knowledge_extractor = KnowledgeExtractor(llm, embedding, graph_provider)
            logger.info("Knowledge extraction enabled (Neo4j graph)")
        elif not graph_provider:
            logger.warning("Knowledge extraction requested but Neo4j not available (set CAIRN_GRAPH_BACKEND=neo4j)")
        elif not llm:
            logger.warning("Knowledge extraction requested but LLM not available")

    # Initialize digest stats
    init_digest_stats()

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
        db, embedding, enricher=enricher, llm=llm, capabilities=capabilities,
        knowledge_extractor=knowledge_extractor,
    )
    project_manager = ProjectManager(db)

    # Legacy search engine (always built — used as fallback for search_v2)
    legacy_search = SearchEngine(
        db, embedding, llm=llm, capabilities=capabilities,
        reranker=reranker, rerank_candidates=config.reranker.candidates,
        activation_engine=activation_engine,
    )

    # Search v2 (optional, intent-routed with graph handlers)
    search_v2 = None
    if capabilities.search_v2:
        search_v2 = SearchV2(
            db=db,
            embedding=embedding,
            graph=graph_provider,
            llm=llm,
            capabilities=capabilities,
            reranker=reranker,
            rerank_candidates=config.reranker.candidates,
            fallback_engine=legacy_search,
        )
        logger.info("Search v2 enabled (intent-routed)")

    # Terminal host manager (optional, based on config)
    terminal_host_manager = None
    if config.terminal.backend != "disabled":
        if config.terminal.backend == "native" and not config.terminal.encryption_key:
            logger.warning("Terminal backend=native but no encryption key — terminal disabled")
        else:
            terminal_host_manager = TerminalHostManager(db, config.terminal)
            logger.info("Terminal enabled: backend=%s", config.terminal.backend)

    return Services(
        config=config,
        db=db,
        embedding=embedding,
        llm=llm,
        enricher=enricher,
        graph_provider=graph_provider,
        knowledge_extractor=knowledge_extractor,
        memory_store=memory_store,
        search_engine=legacy_search,
        search_v2=search_v2,
        cluster_engine=ClusterEngine(db, embedding, llm=llm),
        project_manager=project_manager,
        task_manager=TaskManager(db),
        thinking_engine=ThinkingEngine(db),
        session_synthesizer=SessionSynthesizer(db, llm=llm, capabilities=capabilities),
        consolidation_engine=ConsolidationEngine(db, embedding, llm=llm, capabilities=capabilities),
        cairn_manager=CairnManager(db, llm=llm, capabilities=capabilities),
        digest_worker=DigestWorker(db, llm=llm, capabilities=capabilities),
        drift_detector=DriftDetector(db),
        message_manager=MessageManager(db),
        ingest_pipeline=IngestPipeline(db, project_manager, memory_store, llm, config),
        terminal_host_manager=terminal_host_manager,
        analytics_tracker=analytics_tracker,
        rollup_worker=rollup_worker,
        analytics_engine=analytics_engine,
    )
