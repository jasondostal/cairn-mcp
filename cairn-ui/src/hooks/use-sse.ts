"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * useSSE — subscribe to server-sent events with pattern matching.
 *
 * Connects to GET /api/sse/subscribe?patterns=... and streams matching events.
 * - Auto-reconnects on connection loss with exponential backoff
 * - Visibility-aware: disconnects when tab hidden, reconnects on focus
 * - Returns the latest event for consumers to react to
 *
 * @param patterns Comma-separated event patterns (fnmatch syntax). E.g. "work_item.*,notification.*"
 * @param options.project Optional project filter
 * @param options.enabled Whether to connect (default true)
 * @param options.onEvent Callback for each event
 */

export interface SSEEvent {
  event_type: string;
  event_id?: number;
  session_name?: string;
  project?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

interface UseSSEOptions {
  project?: string;
  enabled?: boolean;
  onEvent?: (event: SSEEvent) => void;
}

interface UseSSEReturn {
  connected: boolean;
  lastEvent: SSEEvent | null;
  reconnectCount: number;
}

const BASE_RETRY_MS = 1000;
const MAX_RETRY_MS = 30_000;

export function useSSE(
  patterns: string,
  options: UseSSEOptions = {},
): UseSSEReturn {
  const { project, enabled = true, onEvent } = options;

  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);
  const [reconnectCount, setReconnectCount] = useState(0);

  const onEventRef = useRef(onEvent);
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  const retryCountRef = useRef(0);
  const sourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<() => void>(() => {});

  const connect = useCallback(() => {
    // Clean up existing connection
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }

    const params = new URLSearchParams({ patterns });
    if (project) params.set("project", project);

    const url = `/api/sse/subscribe?${params.toString()}`;
    const source = new EventSource(url);
    sourceRef.current = source;

    source.addEventListener("connected", () => {
      setConnected(true);
      retryCountRef.current = 0;
    });

    source.addEventListener("event", (e) => {
      try {
        const data: SSEEvent = JSON.parse(e.data);
        setLastEvent(data);
        onEventRef.current?.(data);
      } catch {
        // Ignore malformed events
      }
    });

    source.addEventListener("heartbeat", () => {
      // Connection alive — reset retry counter
      retryCountRef.current = 0;
    });

    source.addEventListener("error", () => {
      // EventSource will auto-reconnect, but we track state
      setConnected(false);
    });

    source.onerror = () => {
      setConnected(false);
      source.close();
      sourceRef.current = null;

      // Exponential backoff retry
      const delay = Math.min(
        BASE_RETRY_MS * Math.pow(2, retryCountRef.current),
        MAX_RETRY_MS,
      );
      retryCountRef.current++;
      setReconnectCount((c) => c + 1);

      reconnectTimerRef.current = setTimeout(() => {
        if (!document.hidden) {
          connectRef.current();
        }
      }, delay);
    };
  }, [patterns, project]);

  useEffect(() => { connectRef.current = connect; }, [connect]);

  // Visibility handling
  useEffect(() => {
    if (!enabled) return;

    function handleVisibility() {
      if (document.hidden) {
        // Disconnect when hidden to save resources
        if (sourceRef.current) {
          sourceRef.current.close();
          sourceRef.current = null;
          setConnected(false);
        }
        if (reconnectTimerRef.current) {
          clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = null;
        }
      } else {
        // Reconnect when visible
        if (!sourceRef.current) {
          retryCountRef.current = 0;
          connect();
        }
      }
    }

    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [enabled, connect]);

  // Main connection lifecycle
  useEffect(() => {
    if (!enabled) {
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
        setConnected(false);
      }
      return;
    }

    connect();

    return () => {
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      setConnected(false);
    };
  }, [enabled, connect]);

  return { connected, lastEvent, reconnectCount };
}
