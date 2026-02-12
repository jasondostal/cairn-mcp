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
from cairn.core.ingest import IngestPipeline
from cairn.core.memory import MemoryStore
from cairn.core.projects import ProjectManager
from cairn.core.search import SearchEngine
from cairn.core.synthesis import SessionSynthesizer
from cairn.core.tasks import TaskManager
from cairn.core.thinking import ThinkingEngine
from cairn.core.stats import init_embedding_stats, init_llm_stats, init_digest_stats
from cairn.embedding import get_embedding_engine
from cairn.embedding.interface import EmbeddingInterface
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
    memory_store: MemoryStore
    search_engine: SearchEngine
    cluster_engine: ClusterEngine
    project_manager: ProjectManager
    task_manager: TaskManager
    thinking_engine: ThinkingEngine
    session_synthesizer: SessionSynthesizer
    consolidation_engine: ConsolidationEngine
    cairn_manager: CairnManager
    digest_worker: DigestWorker
    drift_detector: DriftDetector
    ingest_pipeline: IngestPipeline
    analytics_tracker: UsageTracker | None
    rollup_worker: RollupWorker | None
    analytics_engine: AnalyticsQueryEngine | None


def create_services(config: Config | None = None) -> Services:
    """Build all Cairn services from config.

    Args:
        config: Configuration to use. Loads from env if None.
    """
    if config is None:
        config = load_config()

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

    # Initialize digest stats
    init_digest_stats()

    memory_store = MemoryStore(db, embedding, enricher=enricher, llm=llm, capabilities=capabilities)
    project_manager = ProjectManager(db)

    return Services(
        config=config,
        db=db,
        embedding=embedding,
        llm=llm,
        enricher=enricher,
        memory_store=memory_store,
        search_engine=SearchEngine(db, embedding, llm=llm, capabilities=capabilities),
        cluster_engine=ClusterEngine(db, embedding, llm=llm),
        project_manager=project_manager,
        task_manager=TaskManager(db),
        thinking_engine=ThinkingEngine(db),
        session_synthesizer=SessionSynthesizer(db, llm=llm, capabilities=capabilities),
        consolidation_engine=ConsolidationEngine(db, embedding, llm=llm, capabilities=capabilities),
        cairn_manager=CairnManager(db, llm=llm, capabilities=capabilities),
        digest_worker=DigestWorker(db, llm=llm, capabilities=capabilities),
        drift_detector=DriftDetector(db),
        ingest_pipeline=IngestPipeline(db, project_manager, memory_store, llm, config),
        analytics_tracker=analytics_tracker,
        rollup_worker=rollup_worker,
        analytics_engine=analytics_engine,
    )
