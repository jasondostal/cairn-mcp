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

const RING_SIZE = 60;
const BASE_RETRY_MS = 1000;
const MAX_RETRY_MS = 30_000;

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
  const [state, setState] = useState<MetricsStreamState>({
    buckets: [],
    latest: null,
    connected: false,
  });

  const ringRef = useRef<MetricsBucket[]>([]);
  const sourceRef = useRef<EventSource | null>(null);
  const retryRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<() => void>(() => {});

  const pushBucket = useCallback((bucket: MetricsBucket) => {
    const ring = ringRef.current;
    ring.push(bucket);
    if (ring.length > RING_SIZE) ring.splice(0, ring.length - RING_SIZE);
    setState({ buckets: [...ring], latest: bucket, connected: true });
  }, []);

  const pushBuckets = useCallback((buckets: MetricsBucket[]) => {
    const ring = ringRef.current;
    ring.push(...buckets);
    if (ring.length > RING_SIZE) ring.splice(0, ring.length - RING_SIZE);
    const latest = ring[ring.length - 1] ?? null;
    setState({ buckets: [...ring], latest, connected: true });
  }, []);

  const connect = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }

    const source = new EventSource("/api/metrics/stream?include_history=true");
    sourceRef.current = source;

    source.onopen = () => {
      retryRef.current = 0;
      setState((prev) => (prev.connected ? prev : { ...prev, connected: true }));
    };

    // Batch history buckets that arrive in rapid succession
    let historyBatch: MetricsBucket[] = [];
    let historyTimer: ReturnType<typeof setTimeout> | null = null;

    source.addEventListener("metric", (e) => {
      try {
        const bucket: MetricsBucket = JSON.parse(e.data);
        // If we're still in the initial burst (history), batch them
        if (historyBatch.length > 0 || ringRef.current.length === 0) {
          historyBatch.push(bucket);
          if (historyTimer) clearTimeout(historyTimer);
          historyTimer = setTimeout(() => {
            pushBuckets(historyBatch);
            historyBatch = [];
            historyTimer = null;
          }, 50);
        } else {
          pushBucket(bucket);
        }
        retryRef.current = 0;
      } catch {
        // Ignore malformed
      }
    });

    source.addEventListener("heartbeat", () => {
      retryRef.current = 0;
      setState((prev) => (prev.connected ? prev : { ...prev, connected: true }));
    });

    source.onerror = () => {
      // EventSource fires onerror transiently while CONNECTING — only
      // tear down and retry when the connection is truly CLOSED.
      if (source.readyState === EventSource.CLOSED) {
        setState((prev) => (prev.connected ? { ...prev, connected: false } : prev));
        source.close();
        sourceRef.current = null;

        const delay = Math.min(
          BASE_RETRY_MS * Math.pow(2, retryRef.current),
          MAX_RETRY_MS,
        );
        retryRef.current++;

        timerRef.current = setTimeout(() => {
          if (!document.hidden) connectRef.current();
        }, delay);
      }
    };
  }, [pushBucket, pushBuckets]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Visibility-aware lifecycle
  useEffect(() => {
    function handleVisibility() {
      if (document.hidden) {
        if (sourceRef.current) {
          sourceRef.current.close();
          sourceRef.current = null;
          setState((prev) => ({ ...prev, connected: false }));
        }
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
      } else if (!sourceRef.current) {
        retryRef.current = 0;
        // Clear stale ring on reconnect so we get fresh history
        ringRef.current = [];
        connect();
      }
    }

    document.addEventListener("visibilitychange", handleVisibility);
    connect();

    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [connect]);

  return (
    <MetricsStreamContext.Provider value={state}>
      {children}
    </MetricsStreamContext.Provider>
  );
}
