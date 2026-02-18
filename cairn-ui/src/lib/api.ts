const BASE = "/api";

async function get<T>(path: string, params?: Record<string, string | string[] | undefined>): Promise<T> {
  const url = new URL(path, window.location.origin);
  url.pathname = `${BASE}${path}`;
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v === undefined || v === null) return;
      const str = Array.isArray(v) ? v.join(",") : v;
      if (str !== "") url.searchParams.set(k, str);
    });
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
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
  thoughts: Array<{
    id: number;
    type: string;
    content: string;
    branch: string | null;
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

export interface Message {
  id: number;
  project: string;
  sender: string;
  content: string;
  priority: string;
  is_read: boolean;
  archived: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// --- Work Item types ---

export type WorkItemStatus = "open" | "ready" | "in_progress" | "blocked" | "done" | "cancelled";
export type WorkItemType = "epic" | "task" | "subtask";

export interface WorkItem {
  id: number;
  short_id: string;
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
  short_id: string;
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
  short_id: string;
  project: string;
  title: string;
  description: string | null;
  acceptance_criteria: string | null;
  item_type: WorkItemType;
  priority: number;
  status: WorkItemStatus;
  assignee: string | null;
  parent: { id: number; short_id: string; title: string } | null;
  children_count: number;
  blockers: Array<{ id: number; short_id: string; title: string; status: string }>;
  blocking: Array<{ id: number; short_id: string; title: string; status: string }>;
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
  short_id: string;
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
  items: Array<{ id: number; short_id: string; title: string; priority: number; item_type: string }>;
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
}

export interface WorkspaceSession {
  id: number;
  session_id: string;
  project: string;
  agent: string;
  title: string;
  task: string | null;
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

// --- API functions ---

export const api = {
  status: () => get<Status>("/status"),

  timeline: (opts?: { project?: string; type?: string; session_name?: string; days?: string; limit?: string; offset?: string }) =>
    get<Paginated<TimelineMemory>>("/timeline", opts),

  search: (q: string, opts?: { project?: string; type?: string; mode?: string; limit?: string; offset?: string }) =>
    get<Paginated<Memory>>("/search", { q, ...opts }),

  memory: (id: number) => get<Memory>(`/memories/${id}`),

  memoryWorkItems: (id: number) =>
    get<{ memory_id: number; work_items: Array<{ id: number; short_id: string; title: string; status: string; item_type: string; project: string }> }>(
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

  thinking: (project?: string, opts?: { status?: string; limit?: string; offset?: string }) =>
    get<Paginated<ThinkingSequence>>("/thinking", { ...(project ? { project } : {}), ...opts }),

  thinkingDetail: (id: number) => get<ThinkingDetail>(`/thinking/${id}`),

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

  messages: (opts?: { project?: string; include_archived?: string; limit?: string; offset?: string }) =>
    get<Paginated<Message>>("/messages", opts),

  sendMessage: (body: { content: string; project: string; sender?: string; priority?: string; metadata?: Record<string, unknown> }) =>
    post<{ id: number; created_at: string }>("/messages", body),

  updateMessage: (id: number, body: { is_read?: boolean; archived?: boolean }) =>
    patch<{ updated: boolean; id: number }>(`/messages/${id}`, body),

  markAllMessagesRead: (project?: string) =>
    post<{ action: string; project: string | null }>("/messages/mark-all-read", project ? { project } : {}),

  unreadCount: (project?: string) =>
    get<{ count: number }>("/messages/unread-count", project ? { project } : {}),

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
    project: string; task?: string; message_id?: number; fork_from?: string;
    title?: string; agent?: string; inject_context?: boolean;
    context_mode?: "focused" | "full";
  }) => post<WorkspaceSession>("/workspace/sessions", body),

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

  workItem: (id: number) => get<WorkItemDetail>(`/work-items/${id}`),

  workItemReady: (project: string, limit?: number) =>
    get<ReadyQueue>("/work-items/ready", { project, ...(limit ? { limit: String(limit) } : {}) }),

  workItemCreate: (body: {
    project: string; title: string; description?: string; item_type?: string;
    priority?: number; parent_id?: number; session_name?: string;
    metadata?: Record<string, unknown>; acceptance_criteria?: string;
  }) => post<WorkItemDetail>("/work-items", body),

  workItemUpdate: (id: number, body: {
    title?: string; description?: string; status?: string; priority?: number;
    assignee?: string; item_type?: string; parent_id?: number | null;
    session_name?: string; metadata?: Record<string, unknown>; acceptance_criteria?: string;
  }) => patch<WorkItemDetail>(`/work-items/${id}`, body),

  workItemClaim: (id: number, assignee: string) =>
    post<WorkItemDetail>(`/work-items/${id}/claim`, { assignee }),

  workItemComplete: (id: number) =>
    post<WorkItemDetail>(`/work-items/${id}/complete`, {}),

  workItemAddChild: (parentId: number, body: {
    title: string; description?: string; priority?: number;
    session_name?: string; metadata?: Record<string, unknown>; acceptance_criteria?: string;
  }) => post<WorkItemDetail>(`/work-items/${parentId}/children`, body),

  workItemBlock: (blockerId: number, blockedId: number) =>
    post<{ action: string }>("/work-items/block", { blocker_id: blockerId, blocked_id: blockedId }),

  workItemUnblock: (blockerId: number, blockedId: number) =>
    delWithBody<{ action: string }>("/work-items/block", { blocker_id: blockerId, blocked_id: blockedId }),

  workItemLinkMemories: (id: number, memoryIds: number[]) =>
    post<{ action: string }>(`/work-items/${id}/link-memories`, { memory_ids: memoryIds }),

  workItemSetGate: (id: number, gateType: string, gateData?: Record<string, unknown>, actor?: string) =>
    post<{ action: string }>(`/work-items/${id}/gate`, { gate_type: gateType, gate_data: gateData, actor }),

  workItemResolveGate: (id: number, response?: Record<string, unknown>, actor?: string) =>
    post<{ action: string }>(`/work-items/${id}/gate/resolve`, { response, actor }),

  workItemHeartbeat: (id: number, agentName: string, state?: string, note?: string) =>
    post<{ action: string }>(`/work-items/${id}/heartbeat`, { agent_name: agentName, state, note }),

  workItemActivity: (id: number, opts?: { limit?: string; offset?: string }) =>
    get<{ work_item_id: number; short_id: string; total: number; activities: WorkItemActivity[] }>(
      `/work-items/${id}/activity`, opts
    ),

  workItemBriefing: (id: number) =>
    get<{ work_item: Record<string, unknown>; constraints: Record<string, unknown>; context: Array<Record<string, unknown>>; parent_chain: Array<Record<string, unknown>> }>(
      `/work-items/${id}/briefing`
    ),

  workItemsGated: (opts?: { project?: string; gate_type?: string; limit?: string }) =>
    get<{ total: number; items: GatedItem[] }>("/work-items/gated", opts),

  workItemSessions: (id: number) =>
    get<SessionWorkItemLink[]>(`/work-items/${id}/sessions`),

  sessionWorkItems: (sessionName: string) =>
    get<WorkItemSessionLink[]>(`/sessions/${encodeURIComponent(sessionName)}/work-items`),

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
};
