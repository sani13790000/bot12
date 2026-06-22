/**
 * frontend/src/hooks/useApi.ts
 * FIX-9:  Infinite render loop (fetcherRef pattern)
 * FIX-10: Memory leak (interval + AbortController cleanup)
 * FIX-11: fetch shadows global (renamed execute)
 * FIX-12: loading stuck on abort
 */
import { useState, useEffect, useCallback, useRef } from "react";

interface UseApiOptions {
  autoFetch?: boolean;
  refreshInterval?: number;
  skip?: boolean;
}

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  lastFetched: Date | null;
}

export function useApi<T>(
  fetcher: () => Promise<{ success: boolean; data: T; error?: string }>,
  options: UseApiOptions = {}
) {
  const { autoFetch = true, refreshInterval, skip = false } = options;

  const [state, setState] = useState<UseApiState<T>>({
    data: null, loading: false, error: null, lastFetched: null,
  });

  const fetcherRef  = useRef(fetcher);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef    = useRef<AbortController | null>(null);
  const mountedRef  = useRef(true);

  fetcherRef.current = fetcher;

  const execute = useCallback(async () => {
    if (skip) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setState(s => ({ ...s, loading: true, error: null }));
    try {
      const res = await fetcherRef.current();
      if (!mountedRef.current) return;
      if (res.success) {
        setState({ data: res.data, loading: false, error: null, lastFetched: new Date() });
      } else {
        setState(s => ({ ...s, loading: false, error: res.error ?? "خطای ناشناخته" }));
      }
    } catch (e) {
      if (!mountedRef.current) return;
      const msg = e instanceof Error ? e.message : String(e);
      if (msg !== "AbortError" && msg !== "The user aborted a request.") {
        setState(s => ({ ...s, loading: false, error: msg }));
      }
    }
  }, [skip]);

  useEffect(() => {
    if (autoFetch && !skip) execute();
  }, [autoFetch, skip, execute]);

  useEffect(() => {
    if (!refreshInterval || refreshInterval <= 0 || skip) return;
    intervalRef.current = setInterval(execute, refreshInterval);
    return () => { if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; } };
  }, [refreshInterval, execute, skip]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  return { ...state, refetch: execute };
}
