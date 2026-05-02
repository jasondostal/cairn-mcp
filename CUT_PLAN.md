# Cairn Cut Plan — Memory Brain, Not Agent Body

## Overview

Cairn shrinks from a full-stack agent platform (API + UI + workspace orchestration +
chat + terminal) into a **pure MCP memory server with a web UI console**.

PiClaw owns the agent experience. Cairn owns the memory. The MCP server + search
pipeline + memory CRUD + memory console UI = the product.

## Ground Rules

- **UTIL is production — never touch it.** All changes target CORTEX (nonprod).
  If a config mismatch exists between UTIL and CORTEX, fix CORTEX to match UTIL,
  never the reverse.
- **Git: feature branch `archive/pre-agent-purge`** branched from main. All cuts
  happen here. If it goes sideways, `git branch -D` and walk away. When proven:
  merge to main, tag (e.g. `v0.70.0-memory-slim`), delete branch.
- **Embedding parity is critical.** Before restoring UTIL's prod DB on CORTEX,
  verify the embedding backend + model + dimensions match exactly. Embeddings
  generated with one model are garbage when queried with another.
- **The invariant:** `cairn_memory_search` and `cairn_memory_recall` must continue
  to work. If they break, the branch is dead.

---

## Pre-Flight: Config Parity Audit

Before any cuts, verify CORTEX matches UTIL:

| Config | CORTEX (known) | UTIL (unknown) | Action |
|---|---|---|---|
| `CAIRN_EMBEDDING_BACKEND` | `local` (default) | ? | SSH to UTIL, read .env, reconcile |
| `CAIRN_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | ? | If different, change CORTEX |
| `CAIRN_EMBEDDING_DIMENSIONS` | `384` (default) | ? | If different, change CORTEX |
| `CAIRN_LLM_BACKEND` | `openai` (Groq) | ? | Verify, change CORTEX if needed |
| `CAIRN_NEO4J_PASSWORD` | known | known | Already different (OK for dev) |
| `CAIRN_DB_PASS` | `cairn-prod-2026` | ? | CORTEX already uses prod creds |

**Procedure:** SSH to UTIL, dump .env (read-only), diff against CORTEX .env.
Change CORTEX to match UTIL for embedding + LLM configs only. Never change UTIL.

## Pre-Flight: DB Restore

1. Dump UTIL PostgreSQL + Neo4j (procedure from memory 103)
2. Restore to CORTEX with fresh containers
3. Verify: `cairn_memory_search` returns real results against prod data
4. Verify: `cairn_memory_recall` returns full content by ID
5. If either fails, fix config parity and retry

---

## Phase 1: Kill Agent Infrastructure

### 1a. API routes — DELETE

| Module | Lines | Reason |
|---|---|---|
| `api/chat.py` | ~200 | LLM chat endpoint — PiClaw owns agent chat |
| `api/terminal.py` | ~80 | Terminal host API — PiClaw handles execution |
| `api/conversations.py` | ~100 | Conversation storage — agent concern |
| `api/agents.py` | 46 | Agent registry — orchestrator infrastructure |
| `api/dispatch.py` | ~100 | Workspace dispatch — orchestrator |
| `api/workspace.py` | ~120 | Workspace management — orchestrator |
| `api/deliverables.py` | ~80 | Deliverable API — orphaned without work items |
| `api/sessions.py` | ~100 | Session API — PiClaw owns session tracking, orient() trail is graph-native |

**Gray area — TAG EXPERIMENTAL, don't delete:**
| `api/work_items.py` | ~150 | Work item API — leave for UI observability |

### 1b. Core modules — DELETE

| Module | Lines | Reason |
|---|---|---|
| `core/workspace.py` | 1076 | Workspace backends, dispatch — PiClaw territory |
| `core/conversations.py` | ~200 | Conversation storage |
| `core/agents.py` | ~150 | Agent registry, definitions |
| `core/deliverables.py` | ~200 | Deliverable generation |
| `core/terminal.py` | 225 | Terminal host manager |
| `core/thinking.py` | 442 | Thinking engine was speculative |
| `core/synthesis.py` | 103 | SessionSynthesizer — deprecated v0.58.0, zombie code |
| `core/alerting.py` | 546 | Watchtower Phase 4 — speculative infra |
| `core/alert_worker.py` | ~100 | Worker for alerting |
| `core/retention.py` | 480 | Watchtower Phase 5 — speculative infra |
| `core/retention_worker.py` | ~80 | Worker for retention |
| `core/subscriptions.py` | 412 | Push notification subscriptions |
| `core/webhooks.py` | ~150 | Watchtower Phase 3 |
| `core/webhook_worker.py` | ~80 | Worker for webhooks |
| `core/audit.py` | ~150 | Watchtower Phase 2 — keep if compliance matters |
| `core/analytics.py` | 1075 | Usage tracking/analytics — keep only if UI needs it |
| `core/decay.py` | ~200 | Memory decay — interesting but speculative |
| `core/drift.py` | ~100 | Drift detection — speculative |
| `core/otel.py` | ~100 | OpenTelemetry — speculative |

**Gray area — TAG EXPERIMENTAL:**
| `core/work_items.py` | 1571 | Work item manager — tag, don't delete yet |

**DEFINITELY KEEP (memory core):**
| `core/search.py` | 925 | RRF hybrid search — the heart |
| `core/search_v2.py` | 512 | Unified search wrapper |
| `core/memory.py` | 1200 | MemoryStore — CRUD core |
| `core/activation.py` | 233 | Spreading activation |
| `core/mca.py` | 173 | MCA gate |
| `core/clustering.py` | 658 | HDBSCAN clustering |
| `core/consolidation.py` | 575 | Memory dedup/synthesis |
| `core/enrichment.py` | ~200 | LLM enrichment |
| `core/extraction.py` | ~150 | Knowledge extraction |
| `core/working_memory.py` | 557 | Working memory store |
| `core/beliefs.py` | ~200 | Belief store |
| `core/projects.py` | 478 | Project management |
| `core/user.py` | 767 | User management (auth) |
| `core/ingest.py` | ~300 | Ingest pipeline |
| `core/event_bus.py` | ~250 | Event bus — foundations |
| `core/event_dispatcher.py` | ~150 | Event dispatcher |
| `core/handlers.py` | 429 | Handler utilities |
| `core/oauth2_server.py` | 496 | MCP OAuth |
| `core/constants.py` | 435 | Constants (needs trimming) |
| `core/config.py` | ~300 | Config (needs trimming) |
| `core/services.py` | 562 | Services container (needs heavy trimming) |
| `core/stats.py` | 250 | Stats (embedding/LLM stats used by pipeline) |
| `core/status.py` | 124 | Health status |
| `core/tool_ops.py` | 251 | Tool operation helpers |
| `core/trace.py` | 119 | Tracing |

### 1c. Integrations — DELETE ENTIRE DIRECTORY

| Module | Lines | Reason |
|---|---|---|
| `integrations/interface.py` | 318 | Workspace backend interface |
| `integrations/opencode.py` | 718 | OpenCode backend — already marked deprecated |
| `integrations/claude_code.py` | 501 | Claude Code backend |
| `integrations/agent_sdk.py` | 490 | Agent SDK backend |

All workspace backends are PiClaw territory now.

### 1d. Listeners — DELETE

| Module | Reason |
|---|---|
| `listeners/agent_listener.py` | Agent lifecycle — orchestrator |
| `listeners/deliverable_listener.py` | Deliverable generation |
| `listeners/review_listener.py` | Work item review |
| `listeners/audit_listener.py` | Keep only if audit kept |
| `listeners/webhook_listener.py` | Delete with webhooks |
| `listeners/notification_listener.py` | Delete with subscriptions |
| `listeners/push_notifier.py` | Delete with subscriptions |

**KEEP:**
| `listeners/memory_enrichment.py` | Core memory pipeline |
| `listeners/graph_projection.py` | Neo4j graph sync |
| `listeners/memory_access.py` | Access tracking |
| `listeners/code_index_listener.py` | Keep if code intelligence stays |

### 1e. MCP tools — REVISE

Currently 6 core + 3 extended. After cut:

**Core (always):**
- Memory tools (search, recall, store, modify, delete, consolidate, etc.)
- Project tools (orient, etc.)
- Insights tools

**Extended (gated):**
- Work items tools (if work items kept as experimental)

**Deleted:**
- Session tools (sessions gone, orient() trail is graph-native)
- Agents tools (agent_registry gone)
- Deliverables tools (deliverables gone)
- Locks tools (agent coordination — gone)

### 1f. Config — TRIM

Remove config classes/environment variables for:
- `workspace.*` (all workspace backend config)
- `terminal.*` (terminal host config)
- `alerting.*` (alerting config)
- `retention.*` (retention config)
- `webhooks.*` (webhook config)
- `push.*` (push notification config)
- `router.*` (model router — simplify to single LLM)
- `consolidation_worker.*` (keep only if consolidation worker stays)

Keep:
- `db.*`, `embedding.*`, `llm.*`, `neo4j.*`, `auth.*`, `capabilities.*`
- `reranker.*`, `clustering.*`, `code_intelligence.*`
- `analytics.*` (only if kept)
- `decay.*` (only if kept)

---

## Phase 2: Cairn UI Slimdown

The cairn-ui (9,069 TS/TSX files, 1.5MB source) needs a review pass.
Pages to archive:

- **Chat/Conversations** — DELETE. PiClaw is the chat interface.
- **Terminal** — DELETE. PiClaw handles execution.
- **Workspace management** — DELETE. Orchestrator UI.
- **Agent registry** — DELETE.
- **Dispatch** — DELETE.
- **Sessions browser** — DELETE. PiClaw owns session tracking.

Pages to keep:
- **Search/Memory browser** — KEEP. The core UI value.
- **Memory intelligence** (clusters, entities, relations) — KEEP.
- **Consolidation review** — KEEP.
- **Work items** (if kept experimental) — TAG.
- **Settings/Admin** — KEEP (trimmed to remaining config).

---

## Phase 3: Services Container Rewrite

`core/services.py` (562 lines) loses ~60% of its dependency graph.
Rewrite the `Services` dataclass and `create_services()` to only wire:

```python
@dataclass
class Services:
    config: Config
    db: Database
    embedding: EmbeddingInterface
    llm: LLMInterface | None
    enricher: Enricher | None
    graph_provider: GraphProvider
    knowledge_extractor: KnowledgeExtractor | None
    memory_store: MemoryStore
    search_engine: SearchV2
    cluster_engine: ClusterEngine
    project_manager: ProjectManager
    consolidation_engine: ConsolidationEngine
    consolidation_worker: ConsolidationWorker | None
    event_bus: EventBus
    event_dispatcher: EventDispatcher | None
    drift_detector: DriftDetector | None
    ingest_pipeline: IngestPipeline
    work_item_manager: WorkItemManager | None  # experimental
    user_manager: UserManager | None
    working_memory_store: WorkingMemoryStore
    belief_store: BeliefStore | None
    analytics_tracker: UsageTracker | None
    analytics_engine: AnalyticsQueryEngine | None
    decay_worker: DecayWorker | None
```

Removed from Services:
- `termina_host_manager` (deleted)
- `opencode`, `workspace_backends` (integrations deleted)
- `workspace_manager` (deleted)
- `deliverable_manager` (deleted)
- `conversation_manager` (deleted)
- `session_synthesizer` (sessions deleted)
- `thinking_engine` (deleted)
- `alert_manager`, `alert_worker` (deleted)
- `retention_manager`, `retention_worker` (deleted)
- `subscription_manager` (deleted)
- `webhook_manager`, `webhook_worker` (deleted)
- `audit_manager` (deleted unless compliance needs it)
- `agent_registry` (deleted)
- `rollup_worker` (deleted)

---

## Phase 4: API Route Registration Trim

`api/__init__.py` currently registers 28 route modules. After cut:

**Keep:**
- `core`, `search`, `knowledge`, `events`, `ingest`
- `analytics` (if kept), `export`
- `work_items` (if experimental), `graph_edit`
- `audit` (if kept), `code` (if code intelligence kept)
- `auth_routes`, `working_memory`, `beliefs`, `attachments`

**Delete:**
- `chat`, `terminal`, `conversations`, `agents`, `dispatch`, `workspace`
- `deliverables`, `sessions`, `thinking`
- `alerting`, `retention`, `subscriptions`, `webhooks`

---

## Phase 5: Directory Structure After Cut

```
cairn/
├── api/           # ~13 modules (down from 28)
├── core/          # ~24 modules (down from ~45)
├── code/          # Keep (code intelligence)
├── embedding/     # Keep (unchanged)
├── graph/         # Keep (unchanged)
├── listeners/     # ~4 modules (down from ~12)
├── llm/           # Keep (simplified — single LLM, no router)
├── models/        # Keep (data models)
├── scripts/       # Keep
├── storage/       # Keep (unchanged)
├── tools/         # ~3-4 tool modules (down from 8)
├── server.py      # Keep (MCP server entry point, simplified)
└── config.py      # Trimmed
```

**Deleted directories:**
- `integrations/` — entirely removed

---

## Rough Size Estimate

| Area | Before | After | Delta |
|---|---|---|---|
| Python source | ~50,000 lines | ~26,000-30,000 lines | -40-48% |
| API modules | 28 | 13 | -54% |
| Core modules | ~45 | ~24 | -47% |
| MCP tools | 9+ | 3-4 core | -60% |
| Integrations | 4 files, 2000 lines | 0 | -100% |
| Listeners | 11 | 4 | -64% |

cairn-ui size reduction TBD after page-level audit.

---

## Execution Order

0. **Pre-flight:** Config parity audit — diff UTIL vs CORTEX .env, fix CORTEX to match
1. **Pre-flight:** DB restore — dump UTIL prod DBs, restore to CORTEX, verify search/recall
2. **Branch:** `git checkout -b archive/pre-agent-purge` from main
3. **Phase 1:** Delete agent infrastructure (integrations, chat, terminal, workspace, orchestrator listeners, alerting, retention, webhooks, subscriptions, sessions)
4. **Build/test:** Verify search pipeline still works, MCP tools respond correctly against prod-like data
5. **Phase 2:** Slim cairn-ui (chat/terminal/workspace/session pages)
6. **Phase 3:** Rewrite services.py, trim config
7. **Phase 4:** Clean API route registration
8. **Phase 5:** Trim constants, remove dead config env vars
9. **Merge:** Merge to main, tag `v0.70.0-memory-slim`, delete branch

Each phase independently testable. The invariant: `cairn_memory_search` + `cairn_memory_recall` must work.

No deploy to UTIL until the cut is proven stable on CORTEX with prod-like data.
