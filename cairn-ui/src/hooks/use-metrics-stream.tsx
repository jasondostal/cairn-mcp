"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { MetricsBucket } from "@/lib/api";
import { useSSE, type SSEEvent } from "@/hooks/use-sse";

const RING_SIZE = 60;
const BUCKET_INTERVAL_MS = 5_000;

// ---------------------------------------------------------------------------
// Category mapping — mirrors cairn/core/constants.py EventType.category_for()
// ---------------------------------------------------------------------------

const DOMAIN_CATEGORIES: Record<string, string> = {
  memory: "writes",
  search: "reads",
  work_item: "work",
  deliverable: "work",
  belief: "writes",
  working_memory: "system",
  thinking: "llm",
  settings: "system",
  session: "sessions",
  tool: "tool",
  llm: "llm",
  embed: "embedding",
  api: "api",
  hook: "external",
  code: "system",
};

const CATEGORY_OVERRIDES: Record<string, string> = {
  "memory.recalled": "reads",
  session_start: "sessions",
  session_end: "sessions",
};

function categoryFor(eventType: string): string {
  const override = CATEGORY_OVERRIDES[eventType];
  if (override) return override;
  const prefix = eventType.split(".")[0];
  return DOMAIN_CATEGORIES[prefix] ?? "other";
}

// ---------------------------------------------------------------------------
// Bucket helpers
// ---------------------------------------------------------------------------

function newEmptyBucket(): MetricsBucket {
  return {
    timestamp: new Date().toISOString(),
    ops_count: 0,
    tokens_in: 0,
    tokens_out: 0,
    errors: 0,
    active_sessions: 0,
    by_tool: {},
    by_project: {},
    by_category: {},
    by_event_type: {},
    latency_avg_ms: 0,
  };
}

// Internal tracking fields bolted onto the bucket object
interface BucketInternal {
  _lat_count: number;
  _lat_sum: number;
}

function accumulateEvent(bucket: MetricsBucket, event: SSEEvent): void {
  const eventType = event.event_type ?? "";
  const internal = bucket as unknown as MetricsBucket & BucketInternal;

  bucket.ops_count++;

  // By event type
  bucket.by_event_type[eventType] = (bucket.by_event_type[eventType] ?? 0) + 1;

  // By category
  const cat = categoryFor(eventType);
  bucket.by_category[cat] = (bucket.by_category[cat] ?? 0) + 1;

  // By tool
  const toolName = event.tool_name as string | undefined;
  if (toolName) {
    bucket.by_tool[toolName] = (bucket.by_tool[toolName] ?? 0) + 1;
  }

  // By project
  const projectId = event.project_id as number | undefined;
  if (projectId) {
    const projKey = String(projectId);
    bucket.by_project[projKey] = (bucket.by_project[projKey] ?? 0) + 1;
  }

  // Payload metrics (tokens, latency, errors)
  const payload = event.payload;
  if (payload) {
    const tokIn = typeof payload.tokens_in === "number" ? payload.tokens_in : 0;
    const tokOut =
      typeof payload.tokens_out === "number" ? payload.tokens_out : 0;
    bucket.tokens_in += tokIn;
    bucket.tokens_out += tokOut;

    if (payload.success === false) {
      bucket.errors++;
    }

    const lat =
      typeof payload.latency_ms === "number" ? payload.latency_ms : 0;
    if (lat > 0) {
      const prevCount = internal._lat_count ?? 0;
      const prevSum = internal._lat_sum ?? 0;
      internal._lat_count = prevCount + 1;
      internal._lat_sum = prevSum + lat;
      bucket.latency_avg_ms = internal._lat_sum / internal._lat_count;
    }
  }
}

// ---------------------------------------------------------------------------
// Context + Provider
// ---------------------------------------------------------------------------

interface MetricsStreamState {
  buckets: MetricsBucket[];
  latest: MetricsBucket | null;
  connected: boolean;
}

const MetricsStreamContext = createContext<MetricsStreamState>({
  buckets: [],
  latest: null,
  connected: false,
});

export function useMetricsStream(): MetricsStreamState {
  return useContext(MetricsStreamContext);
}

export function MetricsStreamProvider({ children }: { children: ReactNode }) {
  const [buckets, setBuckets] = useState<MetricsBucket[]>([]);
  const [latest, setLatest] = useState<MetricsBucket | null>(null);

  const ringRef = useRef<MetricsBucket[]>([]);
  const currentBucketRef = useRef<MetricsBucket>(newEmptyBucket());

  // Use the proven useSSE hook — same one that powers notifications
  const onEvent = useCallback((event: SSEEvent) => {
    accumulateEvent(currentBucketRef.current, event);
  }, []);

  const { connected } = useSSE("*", { onEvent });

  // Roll the current bucket into the ring every BUCKET_INTERVAL_MS
  useEffect(() => {
    const tick = setInterval(() => {
      const finished = currentBucketRef.current;
      currentBucketRef.current = newEmptyBucket();

      const ring = ringRef.current;
      ring.push(finished);
      if (ring.length > RING_SIZE) ring.splice(0, ring.length - RING_SIZE);

      setBuckets([...ring]);
      setLatest(finished);
    }, BUCKET_INTERVAL_MS);

    return () => clearInterval(tick);
  }, []);

  const state: MetricsStreamState = { buckets, latest, connected };

  return (
    <MetricsStreamContext.Provider value={state}>
      {children}
    </MetricsStreamContext.Provider>
  );
}
