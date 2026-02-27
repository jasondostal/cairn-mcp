const BASE = "/api";

// ---------------------------------------------------------------------------
// GET cache: deduplicates in-flight requests and caches responses with TTL.
// Mutations (POST/PATCH/DELETE) invalidate matching cache entries.
// ---------------------------------------------------------------------------

interface CacheEntry {
  data: unknown;
  timestamp: number;
}

const DEFAULT_CACHE_TTL = 30_000; // 30s — serve stale while revalidating

const _cache = new Map<string, CacheEntry>();
const _inflight = new Map<string, Promise<unknown>>();

function buildUrl(path: string, params?: Record<string, string | string[] | undefined>): string {
  const url = new URL(path, window.location.origin);
  url.pathname = `${BASE}${path}`;
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v === undefined || v === null) return;
      const str = Array.isArray(v) ? v.join(",") : v;
      if (str !== "") url.searchParams.set(k, str);
    });
  }
  return url.toString();
}

/** Invalidate cache entries whose key starts with the given path prefix. */
export function invalidateCache(pathPrefix?: string) {
  if (!pathPrefix) {
    _cache.clear();
    return;
  }
  const prefix = `${window.location.origin}${BASE}${pathPrefix}`;
  for (const key of _cache.keys()) {
    if (key.startsWith(prefix)) _cache.delete(key);
  }
}

async function get<T>(path: string, params?: Record<string, string | string[] | undefined>): Promise<T> {
  const key = buildUrl(path, params);

  // Deduplicate in-flight requests for the same URL
  const existing = _inflight.get(key);
  if (existing) return existing as Promise<T>;

  const doFetch = async (): Promise<T> => {
    const res = await fetch(key);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data = await res.json();
    _cache.set(key, { data, timestamp: Date.now() });
    return data;
  };

  const promise = doFetch().finally(() => _inflight.delete(key));
  _inflight.set(key, promise);
  return promise;
}

/** Read from cache if fresh, otherwise fetch. Used by useSWR hook. */
export function getCached<T>(
  path: string,
  params?: Record<string, string | string[] | undefined>,
  ttl: number = DEFAULT_CACHE_TTL,
): { cached: T | null; fresh: boolean } {
  const key = buildUrl(path, params);
  const entry = _cache.get(key);
  if (!entry) return { cached: null, fresh: false };
  const age = Date.now() - entry.timestamp;
  return { cached: entry.data as T, fresh: age < ttl };
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `${res.status} ${res.statusText}`);
  }
  // Invalidate GET cache for this resource path
  const basePath = path.replace(/\/[^/]*$/, "");
  invalidateCache(basePath || path);
  return res.json();
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `${res.status} ${res.statusText}`);
  }
  const basePath = path.replace(/\/[^/]*$/, "");
  invalidateCache(basePath || path);
  return res.json();
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

async function delWithBody<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

// --- Types ---

export interface ModelInfo {
  backend: string;
  model: string;
  health: "healthy" | "degraded" | "unhealthy" | "unknown";
  stats: {
    calls: number;
    tokens_est: number;
    errors: number;
    last_call: string | null;
    last_error: string | null;
    last_error_msg: string | null;
  };
}

export interface DigestInfo {
  health: "idle" | "healthy" | "degraded" | "backoff";
  state: string;
  batches_processed: number;
  batches_failed: number;
  events_digested: number;
  queue_depth: number;
  avg_latency_s: number | null;
  last_batch_time: string | null;
  last_error: string | null;
  last_error_msg: string | null;
}

export interface Status {
  version: string;
  status: string;
  memories: number;
  projects: number;
  types: Record<string, number>;
  clusters: number;
  clustering: {
    last_run: string;
    clusters: number;
    memories_clustered: number;
  } | null;
  models: {
    embedding?: ModelInfo;
    llm?: ModelInfo;
  };
  llm_capabilities: string[];
  digest?: DigestInfo;
  graph_backend?: "neo4j" | null;
}

export interface Settings {
  embedding: { backend: string; model: string; dimensions: number };
  llm: { backend: string; model: string };
  reranker: { backend: string; model: string; candidates: number };
  terminal: { backend: string };
  auth: { enabled: boolean };
  analytics: { enabled: boolean; retention_days: number };
  enrichment_enabled: boolean;
  capabilities: Record<string, boolean>;
  transport: string;
  http_port: number;
}

export interface SettingsResponse {
  values: Record<string, string | number | boolean>;
  sources: Record<string, "default" | "env" | "db">;
  editable: string[];
  pending_restart: boolean;
  experimental: string[];
  profiles: string[];
  active_profile: string | null;
}

export interface Project {
  id: number;
  name: string;
  memory_count: number;
  doc_count: number;
  work_item_count: number;
  last_activity: string | null;
  created_at: string;
}

export interface MemoryRelation {
  id: number;
  relation: string;
  direction: "incoming" | "outgoing";
  summary: string;
  memory_type: string;
}

export interface Memory {
  id: number;
  content: string;
  summary: string | null;
  memory_type: string;
  importance: number;
  project: string;
  tags: string[];
  auto_tags: string[];
  related_files: string[];
  is_active: boolean;
  inactive_reason: string | null;
  session_name: string | null;
  created_at: string;
  updated_at: string;
  cluster: { id: number; label: string; size: number } | null;
  relations?: MemoryRelation[];
  score?: number;
  score_components?: { vector: number; recency: number; keyword: number; tag: number };
}

export interface ClusterResult {
  cluster_count: number;
  clusters: Array<{
    id: number;
    label: string;
    summary: string;
    member_count: number;
    confidence: number;
    created_at: string;
    member_ids: number[];
    sample_memories: Array<{ id: number; summary: string; memory_type: string }>;
  }>;
}

export interface Task {
  id: number;
  description: string;
  status: string;
  project?: string;
  linked_memories: number[];
  created_at: string;
  completed_at: string | null;
}

export interface ThinkingSequence {
  sequence_id: number;
  goal: string;
  status: string;
  project?: string;
  thought_count: number;
  created_at: string;
  completed_at: string | null;
}

export interface ThinkingDetail {
  sequence_id: number;
  project: string;
  goal: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  reopened_at: string | null;
  thoughts: Array<{
    id: number;
    type: string;
    content: string;
    branch: string | null;
    author: string | null;
    created_at: string;
  }>;
}

export interface Rule {
  id: number;
  content: string;
  importance: number;
  project: string;
  tags: string[];
  created_at: string;
}

export interface Paginated<T> {
  total: number;
  limit: number | null;
  offset: number;
  items: T[];
}

export interface TimelineMemory {
  id: number;
  summary: string | null;
  content: string;
  memory_type: string;
  importance: number;
  project: string;
  tags: string[];
  auto_tags: string[];
  related_files: string[];
  is_active: boolean;
  session_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface VisualizationPoint {
  id: number;
  x: number;
  y: number;
  summary: string | null;
  memory_type: string;
  cluster_id: number | null;
  cluster_label: string | null;
}

export interface VisualizationResult {
  points: VisualizationPoint[];
  generated_at: string;
}

export interface GraphNode {
  id: number;
  summary: string;
  memory_type: string;
  importance: number;
  project: string;
  created_at: string;
  updated_at: string;
  cluster_id: number | null;
  cluster_label: string | null;
  age_days: number;
  size: number;
}

export interface GraphEdge {
  source: number;
  target: number;
  relation: string;
  created_at: string;
}

export interface GraphResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: {
    node_count: number;
    edge_count: number;
    relation_types: Record<string, number>;
    relation_colors?: Record<string, string>;
  };
}

export interface KnowledgeNode {
  uuid: string;
  name: string;
  entity_type: string;
  project_id: number;
  stmt_count: number;
}

export interface KnowledgeEdge {
  source: string;
  target: string;
  predicate: string;
  fact: string;
  aspect: string;
  episode_id: number;
}

export interface KnowledgeGraphResult {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  stats: {
    node_count: number;
    edge_count: number;
    entity_types: Record<string, number>;
  };
}

export interface Document {
  id: number;
  project: string;
  doc_type: string;
  title: string | null;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface ExportResult {
  project: string;
  exported_at: string;
  memory_count: number;
  memories: Memory[];
}

export interface SessionInfo {
  id: number;
  session_name: string;
  agent_id: string | null;
  agent_type: string | null;
  parent_session: string | null;
  project: string;
  event_count: number;
  started_at: string;
  closed_at: string | null;
  is_active: boolean;
}

export interface SessionEvent {
  id: number;
  session_name: string;
  agent_id: string | null;
  work_item_id: number | null;
  event_type: string;
  tool_name: string | null;
  payload: Record<string, unknown>;
  project: string | null;
  created_at: string;
}

export interface Cairn {
  id: number;
  session_name: string;
  title: string;
  narrative: string | null;
  memory_count: number;
  project?: string;
  started_at: string;
  set_at: string;
  is_compressed: boolean;
}

export interface CairnStone {
  id: number;
  summary: string;
  memory_type: string;
  importance: number;
  tags: string[];
  created_at: string;
}

export interface CairnDetail extends Cairn {
  project: string;
  events: Array<Record<string, unknown>> | null;
  stones: CairnStone[];
}

export interface Conversation {
  id: number;
  title: string | null;
  project: string | null;
  model: string | null;
  message_count: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: number;
  conversation_id: number;
  role: string;
  content: string | null;
  tool_calls: Array<{ name: string; input: Record<string, unknown>; output: unknown }> | null;
  model: string | null;
  token_count: number | null;
  created_at: string;
}

// --- Knowledge Graph entity types ---

export interface KGEntity {
  uuid: string;
  name: string;
  entity_type: string;
  project_id: number;
  stmt_count?: number;
}

export interface KGStatement {
  uuid: string;
  fact: string;
  aspect: string;
  episode_id: number;
  valid_at: string | null;
  invalid_at: string | null;
}

export interface KGEntityDetail extends KGEntity {
  attributes: Record<string, string>;
  statements: KGStatement[];
}

// --- Work Item types ---

export type WorkItemStatus = "open" | "ready" | "in_progress" | "blocked" | "done" | "cancelled";
export type WorkItemType = "epic" | "task" | "subtask";

export interface WorkItem {
  id: number;
  display_id: string;
  title: string;
  item_type: WorkItemType;
  priority: number;
  status: WorkItemStatus;
  assignee: string | null;
  parent_id: number | null;
  project: string;
  children_count: number;
  session_name: string | null;
  risk_tier: number;
  gate_type: string | null;
  agent_state: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface SessionWorkItemLink {
  session_name: string;
  role: string;
  first_seen: string;
  last_seen: string;
  touch_count: number;
  is_active: boolean;
}

export interface WorkItemSessionLink {
  id: number;
  display_id: string;
  title: string;
  status: WorkItemStatus;
  item_type: WorkItemType;
  priority: number;
  assignee: string | null;
  project: string;
  role: string;
  first_seen: string;
  last_seen: string;
  touch_count: number;
}

export interface WorkItemDetail {
  id: number;
  display_id: string;
  project: string;
  title: string;
  description: string | null;
  acceptance_criteria: string | null;
  item_type: WorkItemType;
  priority: number;
  status: WorkItemStatus;
  assignee: string | null;
  parent: { id: number; display_id: string; title: string } | null;
  children_count: number;
  blockers: Array<{ id: number; display_id: string; title: string; status: string }>;
  blocking: Array<{ id: number; display_id: string; title: string; status: string }>;
  linked_memories: Array<{ id: number; summary: string; memory_type: string }>;
  linked_sessions: SessionWorkItemLink[];
  metadata: Record<string, unknown>;
  risk_tier: number;
  gate_type: string | null;
  gate_data: Record<string, unknown>;
  gate_resolved_at: string | null;
  gate_response: Record<string, unknown> | null;
  constraints: Record<string, unknown>;
  agent_state: string | null;
  last_heartbeat: string | null;
  session_name: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
}

export interface WorkItemActivity {
  id: number;
  actor: string | null;
  activity_type: string;
  content: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface GatedItem {
  id: number;
  display_id: string;
  title: string;
  item_type: string;
  priority: number;
  status: string;
  gate_type: string;
  gate_data: Record<string, unknown>;
  risk_tier: number;
  project: string;
}

export interface ReadyQueue {
  project: string;
  items: Array<{ id: number; display_id: string; title: string; priority: number; item_type: string }>;
  source?: string;
}

export interface IngestRequest {
  content?: string;
  url?: string;
  project: string;
  hint?: "auto" | "doc" | "memory" | "both";
  doc_type?: string;
  title?: string;
  source?: string;
  tags?: string[];
  session_name?: string;
  memory_type?: string;
}

export interface IngestResponse {
  status: "ingested" | "duplicate";
  target_type?: string;
  doc_id?: number | null;
  memory_ids?: number[];
  chunk_count?: number;
  existing?: { id: number; source: string; target_type: string; created_at: string };
}

// --- Memory CRUD types ---

export interface StoreMemoryRequest {
  content: string;
  project: string;
  memory_type?: string;
  importance?: number;
  tags?: string[];
  session_name?: string;
  related_files?: string[];
  related_ids?: number[];
  file_hashes?: Record<string, string>;
  author?: string;
}

export interface UpdateMemoryRequest {
  content?: string;
  memory_type?: string;
  importance?: number;
  tags?: string[];
  project?: string;
  author?: string;
}

// --- Code Intelligence types ---

export interface CodeIndexRequest {
  project: string;
  path: string;
  force?: boolean;
}

export interface CodeIndexResult {
  project: string;
  files_scanned: number;
  files_indexed: number;
  files_skipped: number;
  files_deleted: number;
  symbols_created: number;
  imports_created: number;
  errors: string[] | null;
  summary: string;
  bridge?: Record<string, unknown>;
  error?: string;
}

export interface CodeQueryRequest {
  action: string;
  project: string;
  target?: string;
  query?: string;
  kind?: string;
  depth?: number;
  limit?: number;
  mode?: "fulltext" | "semantic";
}

export interface CodeDescribeRequest {
  project: string;
  target?: string;
  kind?: string;
  limit?: number;
}

export interface CodeDescribeResult {
  project: string;
  described: number;
  symbols?: Array<{ qualified_name: string; description: string }>;
  message?: string;
  error?: string;
}

export interface ArchCheckRequest {
  project: string;
  path?: string;
  config_path?: string;
  use_graph?: boolean;
}

export interface ArchCheckResult {
  project: string;
  clean: boolean;
  violations: Array<{
    rule_name: string;
    file_path: string;
    imported_module: string;
    lineno: number;
    description: string;
  }>;
  contract_violations: Array<{
    rule_module: string;
    consumer_file: string;
    imported_name: string;
    lineno: number;
  }>;
  files_checked: number;
  rules_evaluated: number;
  evaluation_mode: "source" | "graph";
  summary: string;
  error?: string;
}

// --- Dispatch types ---

export interface DispatchRequest {
  work_item_id?: number | string;
  project?: string;
  title?: string;
  description?: string;
  backend?: string;
  risk_tier?: number;
  model?: string;
  agent?: string;
  assignee?: string;
}

export interface DispatchResult {
  action: string;
  work_item: {
    id: number;
    display_id: string;
    title: string;
    status: string;
    assignee: string;
  };
  session: {
    id: string;
    backend: string;
  };
  briefing_sent: boolean;
  error?: string;
}

// --- Orient types ---

export interface OrientResult {
  project: string | null;
  rules: Array<Record<string, unknown>>;
  trail: Record<string, unknown>;
  learnings: Array<Record<string, unknown>>;
  work_items: Array<Record<string, unknown>>;
  _budget: { total: number; used: number };
}

// --- Consolidate types ---

export interface ConsolidateResult {
  project: string;
  memory_count: number;
  candidates: Array<Record<string, unknown>>;
  recommendations: Array<Record<string, unknown>>;
  applied: boolean;
  applied_count?: number;
}

// --- Analytics types ---

export interface KpiMetric {
  value: number;
  label: string;
}

export interface SparklinePoint {
  t: string;
  v: number;
}

export interface AnalyticsOverview {
  kpis: {
    operations: KpiMetric;
    tokens: KpiMetric;
    avg_latency: KpiMetric;
    error_rate: KpiMetric;
  };
  sparklines: {
    operations: SparklinePoint[];
    tokens: SparklinePoint[];
    errors: SparklinePoint[];
  };
  days: number;
}

export interface TimeseriesPoint {
  timestamp: string;
  operations: number;
  tokens_in: number;
  tokens_out: number;
  errors: number;
}

export interface AnalyticsTimeseries {
  series: TimeseriesPoint[];
  granularity: string;
  days: number;
}

export interface AnalyticsOperation {
  id: number;
  timestamp: string;
  operation: string;
  project: string | null;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  model: string | null;
  success: boolean;
  error_message: string | null;
  session_name: string | null;
}

export interface ProjectBreakdown {
  project: string;
  operations: number;
  tokens: number;
  avg_latency: number;
  errors: number;
  error_rate: number;
  trend: "up" | "down" | "flat";
}

export interface ModelPerformance {
  model: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  errors: number;
  error_rate: number;
  latency_p50: number;
  latency_p95: number;
  latency_p99: number;
}

// --- Dashboard types ---

export interface EntitySparklines {
  totals: Record<string, number>;
  sparklines: Record<string, SparklinePoint[]>;
  days: number;
}

export interface MemoryGrowthPoint {
  timestamp: string;
  [memoryType: string]: string | number;
}

export interface MemoryGrowthResult {
  series: MemoryGrowthPoint[];
  types: string[];
  days: number;
  granularity: string;
}

export interface HeatmapDay {
  date: string;
  count: number;
}

export interface HeatmapResult {
  days: HeatmapDay[];
}

// --- Workspace types ---

export interface WorkspaceHealth {
  status: "healthy" | "unhealthy" | "not_configured" | "unreachable";
  version?: string;
  error?: string;
  backends?: Record<string, { status: string; version?: string; error?: string }>;
}

export interface WorkspaceBackendInfo {
  name: string;
  status: "healthy" | "unhealthy" | "unreachable";
  version?: string;
  error?: string;
  is_default: boolean;
  capabilities: {
    fork: boolean;
    diff: boolean;
    abort: boolean;
    agents: boolean;
  };
}

export interface WorkspaceSession {
  id: number;
  session_id: string;
  project: string;
  agent: string;
  title: string;
  task: string | null;
  backend?: string;
  created_at: string | null;
  // From create response
  context_injected?: boolean;
  context_length?: number;
  error?: string;
}

export interface WorkspaceMessagePart {
  type: string; // "text" | "tool-invocation" | "tool-result"
  text?: string;
  toolName?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  [key: string]: unknown;
}

export interface WorkspaceMessage {
  id: string;
  role: "user" | "assistant";
  parts: WorkspaceMessagePart[];
  created_at: string | null;
}

export interface WorkspaceAgent {
  id: string;
  name: string | null;
  description: string | null;
  model: string | null;
  backend?: string;
}

// --- Terminal types ---

export interface TerminalConfig {
  backend: "native" | "ttyd" | "disabled";
  max_sessions: number;
}

export interface TerminalHost {
  id: number;
  name: string;
  hostname: string;
  port: number;
  username: string | null;
  auth_method: string;
  ttyd_url: string | null;
  description: string | null;
  is_active: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// --- Watchtower types ---

export interface AlertRule {
  id: number;
  name: string;
  condition_type: string;
  condition: Record<string, unknown>;
  notification: Record<string, unknown> | null;
  severity: string;
  cooldown_minutes: number;
  is_active: boolean;
  last_fired_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertHistoryEntry {
  id: number;
  rule_id: number;
  rule_name: string;
  severity: string;
  message: string;
  value: number | null;
  fired_at: string;
}

export interface AuditEntry {
  id: number;
  trace_id: string | null;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: number | null;
  project: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface Webhook {
  id: number;
  name: string;
  url: string;
  event_types: string[];
  project_id: number | null;
  secret: string;
  is_active: boolean;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface WebhookDelivery {
  id: number;
  webhook_id: number;
  event_type: string;
  status: string;
  http_status: number | null;
  attempts: number;
  last_attempt_at: string | null;
  created_at: string;
}

export interface RetentionPolicy {
  id: number;
  project_id: string | null;
  resource_type: string;
  ttl_days: number;
  legal_hold: boolean;
  is_active: boolean;
  last_run_at: string | null;
  last_deleted: number;
  created_at: string;
  updated_at: string;
}

export interface RetentionStatus {
  total_policies: number;
  active_policies: number;
  held_policies: number;
  last_run_at: string | null;
  earliest_policy: string | null;
  total_deleted: number;
  scan_interval_hours: number;
  dry_run: boolean;
}

// --- API functions ---

export const api = {
  status: () => get<Status>("/status"),

  timeline: (opts?: { project?: string; type?: string; session_name?: string; days?: string; limit?: string; offset?: string }) =>
    get<Paginated<TimelineMemory>>("/timeline", opts),

  search: (q: string, opts?: { project?: string; type?: string; mode?: string; limit?: string; offset?: string }) =>
    get<Paginated<Memory>>("/search", { q, ...opts }),

  memory: (id: number) => get<Memory>(`/memories/${id}`),

  memoryWorkItems: (id: number) =>
    get<{ memory_id: number; work_items: Array<{ id: number; display_id: string; title: string; status: string; item_type: string; project: string }> }>(
      `/memories/${id}/work-items`
    ),

  projects: (opts?: { limit?: string; offset?: string }) =>
    get<Paginated<Project>>("/projects", opts),

  project: (name: string) =>
    get<{ name: string; docs: Array<Record<string, unknown>>; links: Array<Record<string, unknown>> }>(
      `/projects/${encodeURIComponent(name)}`
    ),

  clusters: (opts?: { project?: string; topic?: string }) =>
    get<ClusterResult>("/clusters", opts),

  tasks: (project?: string, opts?: { include_completed?: string; limit?: string; offset?: string }) =>
    get<Paginated<Task>>("/tasks", { ...(project ? { project } : {}), ...opts }),

  taskCreate: (body: { project: string; description: string }) =>
    post<Task>("/tasks", body),

  taskComplete: (id: number) => post<{ status: string }>(`/tasks/${id}/complete`, {}),

  taskPromote: (id: number) =>
    post<{ action: string; task_id: number; work_item: { id: number; display_id: string; title: string; status: string } }>(
      `/tasks/${id}/promote`, {},
    ),

  thinking: (project?: string, opts?: { status?: string; limit?: string; offset?: string }) =>
    get<Paginated<ThinkingSequence>>("/thinking", { ...(project ? { project } : {}), ...opts }),

  thinkingDetail: (id: number) => get<ThinkingDetail>(`/thinking/${id}`),

  thinkingAddThought: (id: number, body: { thought: string; thought_type?: string; author?: string; branch_name?: string }) =>
    post<{ thought_id: number; sequence_id: number; thought_type: string; author: string | null; created_at: string }>(
      `/thinking/${id}/thoughts`, body,
    ),

  thinkingReopen: (id: number) => post<ThinkingDetail>(`/thinking/${id}/reopen`, {}),

  rules: (opts?: { project?: string; limit?: string; offset?: string }) =>
    get<Paginated<Rule>>("/rules", opts),

  clusterVisualization: (opts?: { project?: string }) =>
    get<VisualizationResult>("/clusters/visualization", opts),

  cairns: (project?: string, opts?: { limit?: string }) =>
    get<Cairn[]>("/cairns", { ...(project ? { project } : {}), ...opts }),

  cairnDetail: (id: number) => get<CairnDetail>(`/cairns/${id}`),

  sessions: (opts?: { project?: string; limit?: string }) =>
    get<{ count: number; items: SessionInfo[] }>("/sessions", opts),

  sessionEvents: (sessionName: string, opts?: { project?: string; order?: string }) =>
    get<{ count: number; items: SessionEvent[] }>(`/sessions/${encodeURIComponent(sessionName)}/events`, { order: "asc", ...opts }),

  events: (opts?: { session_name?: string; work_item_id?: string; event_type?: string; project?: string; limit?: string; offset?: string; order?: string }) =>
    get<{ count: number; items: SessionEvent[] }>("/events", { order: "asc", ...opts }),

  graph: (opts?: { project?: string; relation_type?: string; min_importance?: string }) =>
    get<GraphResult>("/graph", opts),

  knowledgeGraph: (opts?: { project?: string; entity_type?: string; limit?: string }) =>
    get<KnowledgeGraphResult>("/knowledge-graph", opts),

  docs: (opts?: { project?: string; doc_type?: string; limit?: string; offset?: string }) =>
    get<Paginated<Document>>("/docs", opts),

  doc: (id: number) => get<Document>(`/docs/${id}`),

  exportProject: (project: string, format: string = "json") =>
    get<ExportResult | string>("/export", { project, format }),

  ingest: (body: IngestRequest) => post<IngestResponse>("/ingest", body),

  chat: (messages: Array<{ role: string; content: string }>, maxTokens?: number, tools?: boolean) =>
    post<{ response: string; model: string; tool_calls?: Array<{ name: string; input: Record<string, unknown>; output: unknown }> }>(
      "/chat", { messages, max_tokens: maxTokens, ...(tools === false ? { tools: false } : {}) }
    ),

  analyticsOverview: (opts?: { days?: string }) =>
    get<AnalyticsOverview>("/analytics/overview", opts),

  analyticsTimeseries: (opts?: { days?: string; granularity?: string; project?: string; operation?: string }) =>
    get<AnalyticsTimeseries>("/analytics/timeseries", opts),

  analyticsOperations: (opts?: { days?: string; project?: string; operation?: string; success?: string; limit?: string; offset?: string }) =>
    get<{ total: number; limit: number; offset: number; items: AnalyticsOperation[] }>("/analytics/operations", opts),

  analyticsProjects: (opts?: { days?: string }) =>
    get<{ items: ProjectBreakdown[]; days: number }>("/analytics/projects", opts),

  analyticsModels: (opts?: { days?: string }) =>
    get<{ items: ModelPerformance[]; days: number }>("/analytics/models", opts),

  analyticsMemoryGrowth: (opts?: { days?: string; granularity?: string }) =>
    get<MemoryGrowthResult>("/analytics/memory-growth", opts),

  analyticsSparklines: (opts?: { days?: string }) =>
    get<EntitySparklines>("/analytics/sparklines", opts),

  analyticsHeatmap: (opts?: { days?: string }) =>
    get<HeatmapResult>("/analytics/heatmap", opts),

  workspaceHealth: () => get<WorkspaceHealth>("/workspace/health"),

  workspaceSessions: (project?: string) =>
    get<WorkspaceSession[]>("/workspace/sessions", project ? { project } : {}),

  workspaceCreateSession: (body: {
    project: string; task?: string; fork_from?: string;
    title?: string; agent?: string; inject_context?: boolean;
    context_mode?: "focused" | "full";
    backend?: string; risk_tier?: number;
    work_item_id?: number | string; model?: string;
  }) => post<WorkspaceSession>("/workspace/sessions", body),

  workspaceBackends: () => get<WorkspaceBackendInfo[]>("/workspace/backends"),

  workspaceGetSession: (sessionId: string) =>
    get<WorkspaceSession>(`/workspace/sessions/${sessionId}`),

  workspaceDeleteSession: (sessionId: string) =>
    del<{ session_id: string; status: string }>(`/workspace/sessions/${sessionId}`),

  workspaceSendMessage: (sessionId: string, body: { text: string; agent?: string; wait?: boolean }) =>
    post<{ session_id: string; response?: string; status?: string }>(`/workspace/sessions/${sessionId}/message`, body),

  workspaceAbortSession: (sessionId: string) =>
    post<{ session_id: string; status: string }>(`/workspace/sessions/${sessionId}/abort`, {}),

  workspaceMessages: (sessionId: string) =>
    get<WorkspaceMessage[]>(`/workspace/sessions/${sessionId}/messages`),

  workspaceAgents: () => get<WorkspaceAgent[]>("/workspace/agents"),

  workspaceDiff: (sessionId: string) =>
    get<Array<Record<string, unknown>>>(`/workspace/sessions/${sessionId}/diff`),

  workspaceContext: (project: string, task?: string) =>
    get<{ context: string }>(`/workspace/context/${encodeURIComponent(project)}`, task ? { task } : {}),

  terminalConfig: () => get<TerminalConfig>("/terminal/config"),

  terminalHosts: () => get<{ items: TerminalHost[] }>("/terminal/hosts"),

  terminalCreateHost: (body: {
    name: string; hostname: string; port?: number;
    username?: string; credential?: string; auth_method?: string;
    ttyd_url?: string; description?: string;
  }) => post<{ id: number; name: string; created_at: string }>("/terminal/hosts", body),

  terminalUpdateHost: (id: number, body: Record<string, unknown>) =>
    patch<{ updated: boolean; id: number }>(`/terminal/hosts/${id}`, body),

  terminalDeleteHost: (id: number) =>
    del<{ deleted: boolean; id: number }>(`/terminal/hosts/${id}`),

  settings: () => get<Settings>("/settings"),

  settingsV2: () => get<SettingsResponse>("/settings"),

  updateSettings: (body: Record<string, string | number | boolean>) =>
    patch<SettingsResponse>("/settings", body),

  resetSetting: (key: string) =>
    del<SettingsResponse>(`/settings/${key}`),

  // --- Work Items ---

  workItems: (opts?: { project?: string; status?: string; item_type?: string; assignee?: string; include_children?: string; limit?: string; offset?: string }) =>
    get<Paginated<WorkItem>>("/work-items", opts),

  workItem: (id: number | string) => get<WorkItemDetail>(`/work-items/${id}`),

  workItemReady: (project: string, limit?: number) =>
    get<ReadyQueue>("/work-items/ready", { project, ...(limit ? { limit: String(limit) } : {}) }),

  workItemCreate: (body: {
    project: string; title: string; description?: string; item_type?: string;
    priority?: number; parent_id?: number; session_name?: string;
    metadata?: Record<string, unknown>; acceptance_criteria?: string;
  }) => post<WorkItemDetail>("/work-items", body),

  workItemUpdate: (id: number | string, body: {
    title?: string; description?: string; status?: string; priority?: number;
    assignee?: string; item_type?: string; parent_id?: number | null;
    session_name?: string; metadata?: Record<string, unknown>; acceptance_criteria?: string;
  }) => patch<WorkItemDetail>(`/work-items/${id}`, body),

  workItemClaim: (id: number | string, assignee: string) =>
    post<WorkItemDetail>(`/work-items/${id}/claim`, { assignee }),

  workItemComplete: (id: number | string) =>
    post<WorkItemDetail>(`/work-items/${id}/complete`, {}),

  workItemAddChild: (parentId: number | string, body: {
    title: string; description?: string; priority?: number;
    session_name?: string; metadata?: Record<string, unknown>; acceptance_criteria?: string;
  }) => post<WorkItemDetail>(`/work-items/${parentId}/children`, body),

  workItemBlock: (blockerId: number | string, blockedId: number | string) =>
    post<{ action: string }>("/work-items/block", { blocker_id: blockerId, blocked_id: blockedId }),

  workItemUnblock: (blockerId: number | string, blockedId: number | string) =>
    delWithBody<{ action: string }>("/work-items/block", { blocker_id: blockerId, blocked_id: blockedId }),

  workItemLinkMemories: (id: number | string, memoryIds: number[]) =>
    post<{ action: string }>(`/work-items/${id}/link-memories`, { memory_ids: memoryIds }),

  workItemSetGate: (id: number | string, gateType: string, gateData?: Record<string, unknown>, actor?: string) =>
    post<{ action: string }>(`/work-items/${id}/gate`, { gate_type: gateType, gate_data: gateData, actor }),

  workItemResolveGate: (id: number | string, response?: Record<string, unknown>, actor?: string) =>
    post<{ action: string }>(`/work-items/${id}/gate/resolve`, { response, actor }),

  workItemHeartbeat: (id: number | string, agentName: string, state?: string, note?: string) =>
    post<{ action: string }>(`/work-items/${id}/heartbeat`, { agent_name: agentName, state, note }),

  workItemActivity: (id: number | string, opts?: { limit?: string; offset?: string }) =>
    get<{ work_item_id: number; display_id: string; total: number; activities: WorkItemActivity[] }>(
      `/work-items/${id}/activity`, opts
    ),

  workItemBriefing: (id: number | string) =>
    get<{ work_item: Record<string, unknown>; constraints: Record<string, unknown>; context: Array<Record<string, unknown>>; parent_chain: Array<Record<string, unknown>> }>(
      `/work-items/${id}/briefing`
    ),

  workItemsGated: (opts?: { project?: string; gate_type?: string; limit?: string }) =>
    get<{ total: number; items: GatedItem[] }>("/work-items/gated", opts),

  workItemSessions: (id: number | string) =>
    get<SessionWorkItemLink[]>(`/work-items/${id}/sessions`),

  sessionWorkItems: (sessionName: string) =>
    get<WorkItemSessionLink[]>(`/sessions/${encodeURIComponent(sessionName)}/work-items`),

  // --- Memory CRUD ---

  storeMemory: (body: StoreMemoryRequest) =>
    post<Memory>("/memories", body),

  updateMemory: (id: number, body: UpdateMemoryRequest) =>
    patch<Memory>(`/memories/${id}`, body),

  inactivateMemory: (id: number, reason: string) =>
    post<Record<string, unknown>>(`/memories/${id}/inactivate`, { reason }),

  reactivateMemory: (id: number) =>
    post<Record<string, unknown>>(`/memories/${id}/reactivate`, {}),

  recallMemories: (ids: number[]) =>
    post<Memory[]>("/memories/recall", { ids }),

  // --- Analysis ---

  consolidate: (project: string, dryRun?: boolean) =>
    post<ConsolidateResult>("/consolidate", { project, dry_run: dryRun ?? true }),

  orient: (project?: string) =>
    post<OrientResult>("/orient", { project }),

  // --- Project mutations ---

  linkProjects: (source: string, target: string, linkType?: string) =>
    post<Record<string, unknown>>(`/projects/${encodeURIComponent(source)}/links`, { target, link_type: linkType ?? "related" }),

  updateDoc: (docId: number, body: { content: string; title?: string }) =>
    patch<Document>(`/docs/${docId}`, body),

  // --- Code Intelligence ---

  codeIndex: (body: CodeIndexRequest) =>
    post<CodeIndexResult>("/code/index", body),

  codeQuery: (body: CodeQueryRequest) =>
    post<Record<string, unknown>>("/code/query", body),

  codeDescribe: (body: CodeDescribeRequest) =>
    post<CodeDescribeResult>("/code/describe", body),

  archCheck: (body: ArchCheckRequest) =>
    post<ArchCheckResult>("/code/arch-check", body),

  // --- Dispatch ---

  dispatch: (body: DispatchRequest) =>
    post<DispatchResult>("/dispatch", body),

  // --- Conversations ---

  conversations: (opts?: { project?: string; limit?: string; offset?: string }) =>
    get<Paginated<Conversation>>("/chat/conversations", opts),

  conversation: (id: number) => get<Conversation>(`/chat/conversations/${id}`),

  createConversation: (body: { project?: string; title?: string; model?: string }) =>
    post<Conversation>("/chat/conversations", body),

  updateConversation: (id: number, body: { title: string }) =>
    patch<Conversation>(`/chat/conversations/${id}`, body),

  deleteConversation: (id: number) =>
    del<{ deleted: boolean; id: number }>(`/chat/conversations/${id}`),

  conversationMessages: (id: number, opts?: { limit?: string; offset?: string }) =>
    get<{ conversation_id: number; messages: ChatMessage[] }>(
      `/chat/conversations/${id}/messages`, opts,
    ),

  addConversationMessage: (id: number, body: {
    role: string; content?: string; tool_calls?: Array<Record<string, unknown>>;
    model?: string; token_count?: number;
  }) => post<ChatMessage>(`/chat/conversations/${id}/messages`, body),

  // --- Knowledge Graph Entities ---

  entities: (opts: { project: string; search?: string; entity_type?: string; limit?: string }) =>
    get<{ items: KGEntity[]; total: number }>("/entities", opts),

  entity: (uuid: string) =>
    get<KGEntityDetail>(`/entities/${uuid}`),

  createEntity: (body: { name: string; entity_type: string; project: string }) =>
    post<KGEntity>("/entities", body),

  updateEntity: (uuid: string, body: { name?: string; entity_type?: string }) =>
    patch<KGEntity>(`/entities/${uuid}`, body),

  deleteEntity: (uuid: string) =>
    del<{ entity_deleted: boolean; orphaned_statements_deleted: number }>(`/entities/${uuid}`),

  mergeEntities: (body: { canonical_id: string; duplicate_id: string }) =>
    post<{ subject_edges_moved: number; object_edges_moved: number; duplicate_deleted: string }>(
      "/entities/merge", body,
    ),

  entityStatements: (uuid: string, opts?: { aspects?: string }) =>
    get<{ entity_uuid: string; statements: KGStatement[] }>(`/entities/${uuid}/statements`, opts),

  invalidateStatement: (uuid: string, opts?: { invalidated_by?: string }) =>
    post<{ invalidated: boolean; uuid: string }>(`/statements/${uuid}/invalidate`, opts),

  // --- Watchtower: Alerts ---

  alertRules: (opts?: { is_active?: string; severity?: string; limit?: string; offset?: string }) =>
    get<Paginated<AlertRule>>("/alerts/rules", opts),

  alertRuleCreate: (body: {
    name: string; condition_type: string; condition: Record<string, unknown>;
    notification?: Record<string, unknown>; severity?: string; cooldown_minutes?: number;
  }) => post<AlertRule>("/alerts/rules", body),

  alertRuleUpdate: (id: number, body: Record<string, unknown>) =>
    patch<AlertRule>(`/alerts/rules/${id}`, body),

  alertRuleDelete: (id: number) =>
    del<{ deleted: boolean }>(`/alerts/rules/${id}`),

  alertHistory: (opts?: { rule_id?: string; severity?: string; days?: string; limit?: string; offset?: string }) =>
    get<Paginated<AlertHistoryEntry>>("/alerts/history", opts),

  alertActive: (opts?: { hours?: string }) =>
    get<{ active: AlertHistoryEntry[] }>("/alerts/active", opts),

  alertTemplates: () =>
    get<{ templates: Record<string, Record<string, unknown>> }>("/alerts/templates"),

  // --- Watchtower: Audit ---

  auditQuery: (opts?: {
    trace_id?: string; actor?: string; action?: string;
    resource_type?: string; project?: string; days?: string;
    limit?: string; offset?: string;
  }) => get<Paginated<AuditEntry>>("/audit", opts),

  auditGet: (id: number) => get<AuditEntry>(`/audit/${id}`),

  auditByTrace: (traceId: string) =>
    get<Paginated<AuditEntry>>(`/audit/trace/${traceId}`),

  // --- Watchtower: Webhooks ---

  webhooks: (opts?: { project?: string; active_only?: string; limit?: string; offset?: string }) =>
    get<Paginated<Webhook>>("/webhooks", opts),

  webhookCreate: (body: { name: string; url: string; event_types: string[]; project?: string; metadata?: Record<string, unknown> }) =>
    post<Webhook>("/webhooks", body),

  webhookUpdate: (id: number, body: Record<string, unknown>) =>
    patch<Webhook>(`/webhooks/${id}`, body),

  webhookDelete: (id: number) =>
    del<{ status: string }>(`/webhooks/${id}`),

  webhookTest: (id: number) =>
    post<{ status: string; http_status?: number; error?: string }>(`/webhooks/${id}/test`, {}),

  webhookRotateSecret: (id: number) =>
    post<Webhook>(`/webhooks/${id}/rotate-secret`, {}),

  webhookDeliveries: (id: number, opts?: { status?: string; limit?: string; offset?: string }) =>
    get<Paginated<WebhookDelivery>>(`/webhooks/${id}/deliveries`, opts),

  // --- Watchtower: Retention ---

  retentionPolicies: (opts?: { resource_type?: string; project_id?: string; is_active?: string; limit?: string; offset?: string }) =>
    get<Paginated<RetentionPolicy>>("/retention/policies", opts),

  retentionPolicyCreate: (body: { resource_type: string; ttl_days: number; project_id?: string; legal_hold?: boolean }) =>
    post<RetentionPolicy>("/retention/policies", body),

  retentionPolicyUpdate: (id: number, body: Record<string, unknown>) =>
    patch<RetentionPolicy>(`/retention/policies/${id}`, body),

  retentionPolicyDelete: (id: number) =>
    del<{ deleted: boolean }>(`/retention/policies/${id}`),

  retentionPreview: (policyId?: number) =>
    post<{ results: Array<{ policy_id: number; resource_type: string; would_delete: number; reason?: string }> }>(
      "/retention/preview", policyId ? { policy_id: policyId } : {},
    ),

  retentionStatus: () => get<RetentionStatus>("/retention/status"),
};
