const BASE = "/api";

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, window.location.origin);
  url.pathname = `${BASE}${path}`;
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
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

export interface Project {
  id: number;
  name: string;
  memory_count: number;
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

// --- API functions ---

export const api = {
  status: () => get<Status>("/status"),

  timeline: (opts?: { project?: string; type?: string; days?: string; limit?: string; offset?: string }) =>
    get<Paginated<TimelineMemory>>("/timeline", opts),

  search: (q: string, opts?: { project?: string; type?: string; mode?: string; limit?: string; offset?: string }) =>
    get<Paginated<Memory>>("/search", { q, ...opts }),

  memory: (id: number) => get<Memory>(`/memories/${id}`),

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

  graph: (opts?: { project?: string; relation_type?: string; min_importance?: string }) =>
    get<GraphResult>("/graph", opts),

  docs: (opts?: { project?: string; doc_type?: string; limit?: string; offset?: string }) =>
    get<Paginated<Document>>("/docs", opts),

  doc: (id: number) => get<Document>(`/docs/${id}`),

  exportProject: (project: string, format: string = "json") =>
    get<ExportResult | string>("/export", { project, format }),

  ingest: (body: IngestRequest) => post<IngestResponse>("/ingest", body),
};
