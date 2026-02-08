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

// --- Types ---

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
  embedding_model: string;
  embedding_dimensions: number;
  llm_backend: string;
  llm_model: string;
}

export interface Project {
  id: number;
  name: string;
  memory_count: number;
  created_at: string;
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
  score?: number;
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
  linked_memories: number[];
  created_at: string;
  completed_at: string | null;
}

export interface ThinkingSequence {
  sequence_id: number;
  goal: string;
  status: string;
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

export interface ExportResult {
  project: string;
  exported_at: string;
  memory_count: number;
  memories: Memory[];
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

  tasks: (project: string, opts?: { include_completed?: string; limit?: string; offset?: string }) =>
    get<Paginated<Task>>("/tasks", { project, ...opts }),

  thinking: (project: string, opts?: { status?: string; limit?: string; offset?: string }) =>
    get<Paginated<ThinkingSequence>>("/thinking", { project, ...opts }),

  thinkingDetail: (id: number) => get<ThinkingDetail>(`/thinking/${id}`),

  rules: (opts?: { project?: string; limit?: string; offset?: string }) =>
    get<Paginated<Rule>>("/rules", opts),

  clusterVisualization: (opts?: { project?: string }) =>
    get<VisualizationResult>("/clusters/visualization", opts),

  exportProject: (project: string, format: string = "json") =>
    get<ExportResult | string>("/export", { project, format }),
};
