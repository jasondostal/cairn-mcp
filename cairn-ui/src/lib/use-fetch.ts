"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UseFetchResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** True when serving stale data while revalidating in background */
  isValidating: boolean;
  refetch: () => void;
}

/**
 * SWR-style data fetching hook.
 *
 * On mount: serves cached data instantly (if available) while revalidating
 * in the background. If no cached data, shows loading state until fetch completes.
 *
 * Deduplicates fetches — identical fetcher calls within the same render cycle
 * share a single promise (handled by the api.ts cache layer).
 */
export function useFetch<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = []
): UseFetchResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [tick, setTick] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    let cancelled = false;

    // If we already have data (from cache or previous fetch), show it
    // and revalidate in background without flashing loading state
    if (data !== null) {
      setIsValidating(true);
      setError(null);
      fetcher()
        .then((result) => {
          if (!cancelled && mountedRef.current) {
            setData(result);
            setError(null);
          }
        })
        .catch((err) => {
          // Keep stale data on revalidation failure — don't flash error
          if (!cancelled && mountedRef.current) {
            setError(err?.message || "Failed to load data");
          }
        })
        .finally(() => {
          if (!cancelled && mountedRef.current) setIsValidating(false);
        });
    } else {
      // First load — no cached data, show loading spinner
      setLoading(true);
      setError(null);
      fetcher()
        .then((result) => {
          if (!cancelled && mountedRef.current) setData(result);
        })
        .catch((err) => {
          if (!cancelled && mountedRef.current)
            setError(err?.message || "Failed to load data");
        })
        .finally(() => {
          if (!cancelled && mountedRef.current) setLoading(false);
        });
    }

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return { data, loading, error, isValidating, refetch };
}
