"""Service container and factory. Centralizes component initialization."""

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
from cairn.core.conversations import ConversationManager
from cairn.core.deliverables import DeliverableManager
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
    init_event_bus_stats,
    init_llm_stats,
    init_metrics_collector,
)
from cairn.core.synthesis import SessionSynthesizer
from cairn.core.terminal import TerminalHostManager
from cairn.core.thinking import ThinkingEngine
from cairn.core.user import UserManager
from cairn.core.work_items import WorkItemManager
from cairn.core.working_memory import WorkingMemoryStore
from cairn.core.workspace import WorkspaceManager
from cairn.embedding import get_embedding_engine
from cairn.embedding.interface import EmbeddingInterface
from cairn.graph import get_graph_provider
from cairn.graph.interface import GraphProvider
from cairn.integrations.interface import WorkspaceBackend
from cairn.integrations.opencode import OpenCodeBackend, OpenCodeClient
from cairn.llm import get_llm
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.core.agents import AgentRegistry
    from cairn.core.alert_worker import AlertEvaluator
    from cairn.core.alerting import AlertManager
    from cairn.core.audit import AuditManager
    from cairn.core.beliefs import BeliefStore
    from cairn.core.consolidation import ConsolidationWorker
    from cairn.core.decay import DecayWorker
    from cairn.core.metrics_collector import MetricsCollector
    from cairn.core.retention import RetentionManager
    from cairn.core.retention_worker import RetentionWorker
    from cairn.core.subscriptions import SubscriptionManager
    from cairn.core.webhook_worker import WebhookDeliveryWorker
    from cairn.core.webhooks import WebhookManager
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
    thinking_engine: ThinkingEngine
    session_synthesizer: SessionSynthesizer
    consolidation_engine: ConsolidationEngine
    event_bus: EventBus
    drift_detector: DriftDetector
    ingest_pipeline: IngestPipeline
    terminal_host_manager: TerminalHostManager | None
    opencode: OpenCodeClient | None  # deprecated — use workspace_backends
    workspace_backends: dict[str, WorkspaceBackend]
    workspace_manager: WorkspaceManager
    work_item_manager: WorkItemManager
    deliverable_manager: DeliverableManager
    conversation_manager: ConversationManager
    event_dispatcher: EventDispatcher | None
    analytics_tracker: UsageTracker | None
    rollup_worker: RollupWorker | None
    decay_worker: DecayWorker | None
    analytics_engine: AnalyticsQueryEngine | None
    audit_manager: AuditManager | None
    webhook_manager: WebhookManager | None
    webhook_worker: WebhookDeliveryWorker | None
    alert_manager: AlertManager | None
    alert_worker: AlertEvaluator | None
    retention_manager: RetentionManager | None
    retention_worker: RetentionWorker | None
    subscription_manager: SubscriptionManager | None
    agent_registry: AgentRegistry | None
    user_manager: UserManager | None
    working_memory_store: WorkingMemoryStore
    belief_store: BeliefStore | None
    consolidation_worker: ConsolidationWorker | None
    metrics_collector: MetricsCollector | None


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

    # Warn if Neo4j appears configured but knowledge_extraction is off
    if not capabilities.knowledge_extraction:
        neo4j_uri = config.neo4j.uri
        if neo4j_uri and neo4j_uri != "bolt://localhost:7687":
            # Non-default Neo4j URI suggests intentional Neo4j setup
            logger.warning(
                "Neo4j configured (%s) but knowledge_extraction disabled. "
                "Graph trail and entity search will have limited data. "
                "Set CAIRN_KNOWLEDGE_EXTRACTION=true or use 'knowledge' profile.",
                neo4j_uri,
            )

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

    # Wire event_bus into memory_store (created before event_bus for DI ordering)
    memory_store.event_bus = event_bus

    # Register memory enrichment listener (async graph persist + relationships)
    from cairn.listeners.memory_enrichment import MemoryEnrichmentListener
    _memory_listener = MemoryEnrichmentListener(memory_store)
    _memory_listener.register(event_bus)
    logger.info("MemoryEnrichmentListener registered with EventBus")

    # NOTE: SessionSynthesisListener removed (v0.58.0). The v0.50.0 architecture
    # decision (memory #256) killed LLM synthesis — organic memories from agents
    # are the high-signal path, orient() trail provides session context via the
    # knowledge graph. The listener was a regression that produced low-value
    # duplicate summaries.

    # Register graph projection listener if graph is available
    if graph_provider:
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
    if graph_provider and capabilities.code_intelligence:
        from cairn.listeners.code_index_listener import CodeIndexListener
        _code_listener = CodeIndexListener(graph_provider, db)
        _code_listener.register(event_bus)
        logger.info("CodeIndexListener registered with EventBus")

    # Work item + deliverable managers — created early for listener registration
    _wi_mgr = WorkItemManager(
        db, embedding, graph=graph_provider,
        knowledge_extractor=knowledge_extractor,
        event_bus=event_bus,
    )
    _deliverable_mgr = DeliverableManager(db, event_bus=event_bus)

    # Deliverable auto-generation listener — creates deliverables on work item completion
    from cairn.listeners.deliverable_listener import DeliverableListener
    _deliverable_listener = DeliverableListener(
        deliverable_manager=_deliverable_mgr,
        work_item_manager=_wi_mgr,
        db=db,
        llm=llm_fast,
    )
    _deliverable_listener.register(event_bus)
    logger.info("DeliverableListener registered with EventBus")

    # Review listener — handles work item state changes on deliverable approve/revise/reject
    from cairn.listeners.review_listener import ReviewListener
    _review_listener = ReviewListener(
        work_item_manager=_wi_mgr,
        db=db,
    )
    _review_listener.register(event_bus)
    logger.info("ReviewListener registered with EventBus")

    # Audit listener — append-only compliance log for mutation events (Watchtower Phase 2)
    audit_manager = None
    if config.audit.enabled:
        from cairn.core.audit import AuditManager
        from cairn.listeners.audit_listener import AuditListener
        audit_manager = AuditManager(db)
        _audit_listener = AuditListener(audit_manager)
        _audit_listener.register(event_bus)
        logger.info("AuditListener registered with EventBus")

    # Webhook subscriptions — push events to external HTTP endpoints (Watchtower Phase 3)
    webhook_manager = None
    webhook_worker = None
    if config.webhooks.enabled:
        from cairn.core.webhook_worker import WebhookDeliveryWorker
        from cairn.core.webhooks import WebhookManager
        from cairn.listeners.webhook_listener import WebhookListener
        webhook_manager = WebhookManager(db, config.webhooks)
        _webhook_listener = WebhookListener(webhook_manager)
        _webhook_listener.register(event_bus)
        webhook_worker = WebhookDeliveryWorker(db, config.webhooks)
        logger.info("WebhookListener registered with EventBus")

    # Health alerting — rule evaluation + webhook delivery (Watchtower Phase 4)
    alert_manager = None
    alert_worker = None
    if config.alerting.enabled:
        from cairn.core.alert_worker import AlertEvaluator
        from cairn.core.alerting import AlertManager
        alert_manager = AlertManager(db, config.alerting)
        alert_worker = AlertEvaluator(db, alert_manager, webhook_manager, config.alerting)
        logger.info("AlertEvaluator enabled (interval=%ds)", config.alerting.eval_interval_seconds)

    # Data retention — scheduled cleanup of old data (Watchtower Phase 5)
    retention_manager = None
    retention_worker = None
    if config.retention.enabled:
        from cairn.core.retention import RetentionManager
        from cairn.core.retention_worker import RetentionWorker
        retention_manager = RetentionManager(db, config.retention)
        retention_worker = RetentionWorker(retention_manager, config.retention)
        logger.info("RetentionWorker enabled (interval=%dh, dry_run=%s)",
                     config.retention.scan_interval_hours, config.retention.dry_run)

    # Push notifications via ntfy.sh (ca-148)
    from cairn.listeners.push_notifier import PushNotifier
    push_notifier: PushNotifier | None = None
    if config.push.enabled and config.push.url:
        push_notifier = PushNotifier(config.push)
        logger.info("PushNotifier enabled (url=%s, topic=%s)",
                     config.push.url, config.push.default_topic)

    # Event subscriptions + notifications (ca-146)
    from cairn.core.subscriptions import SubscriptionManager
    from cairn.listeners.notification_listener import NotificationListener
    subscription_manager = SubscriptionManager(db, push_notifier=push_notifier)
    _notification_listener = NotificationListener(subscription_manager)
    _notification_listener.register(event_bus)
    logger.info("NotificationListener registered with EventBus")

    # Agent type registry (ca-150)
    from cairn.core.agents import AgentRegistry
    agent_registry = AgentRegistry()
    logger.info("AgentRegistry initialized with %d definitions", len(agent_registry.list()))

    # User manager (ca-124) — created when auth is enabled with JWT
    _user_manager = None
    if config.auth.enabled and config.auth.jwt_secret:
        _user_manager = UserManager(db)
        logger.info("UserManager initialized (JWT auth enabled)")

    # OTel export — optional bridge to external observability (Watchtower Phase 6)
    from cairn.core import otel
    otel.init(config.otel)

    # Event dispatcher — background delivery worker (started in _start_workers)
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
            ssh_host=config.workspace.claude_code_ssh_host,
            ssh_user=config.workspace.claude_code_ssh_user,
            ssh_key_path=config.workspace.claude_code_ssh_key,
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
        cluster_engine=_cluster_engine,
        project_manager=project_manager,
        work_item_manager=_wi_mgr,
        deliverable_manager=_deliverable_mgr,
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
        event_bus=event_bus,
        event_dispatcher=event_dispatcher,
        drift_detector=DriftDetector(db),
        ingest_pipeline=IngestPipeline(db, project_manager, memory_store, llm_fast, config),
        terminal_host_manager=terminal_host_manager,
        opencode=opencode,
        workspace_backends=workspace_backends,
        workspace_manager=WorkspaceManager(
            db, workspace_backends,
            default_backend=config.workspace.default_backend,
            work_item_manager=_wi_mgr,
            default_agent=config.workspace.default_agent,
            budget_tokens=config.budget.workspace,
        ),
        conversation_manager=ConversationManager(db, llm=llm_fast),
        analytics_tracker=analytics_tracker,
        rollup_worker=rollup_worker,
        decay_worker=decay_worker,
        analytics_engine=analytics_engine,
        audit_manager=audit_manager,
        webhook_manager=webhook_manager,
        webhook_worker=webhook_worker,
        alert_manager=alert_manager,
        alert_worker=alert_worker,
        retention_manager=retention_manager,
        retention_worker=retention_worker,
        subscription_manager=subscription_manager,
        agent_registry=agent_registry,
        user_manager=_user_manager,
        working_memory_store=WorkingMemoryStore(
            db, embedding=embedding, event_bus=event_bus,
            memory_store=memory_store, belief_store=_belief_store,
        ),
        belief_store=_belief_store,
        consolidation_worker=_consolidation_worker,
        metrics_collector=_build_metrics_collector(event_bus),
    )


def _build_metrics_collector(event_bus):
    from cairn.core.metrics_collector import MetricsCollector

    collector = MetricsCollector()
    # Wire to EventBus for domain events (memory, search, work items)
    event_bus.add_observer(collector.handle_event)
    # Wire to stats module for LLM/embedding usage events
    init_metrics_collector(collector)
    return collector
