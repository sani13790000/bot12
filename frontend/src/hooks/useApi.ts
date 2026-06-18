import { useState, useEffect, useCallback, useRef } from "react";

interface UseApiOptions {
  autoFetch?: boolean;
  refreshInterval?: number;
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
  const { autoFetch = true, refreshInterval } = options;
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: false,
    error: null,
    lastFetched: null,
  });
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetch = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await fetcher();
      if (res.success) {
        setState({ data: res.data, loading: false, error: null, lastFetched: new Date() });
      } else {
        setState((s) => ({ ...s, loading: false, error: res.error ?? "خطای ناشناخته" }));
      }
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: String(e) }));
    }
  }, [fetcher]);

  useEffect(() => {
    if (autoFetch) fetch();
  }, [autoFetch, fetch]);

  useEffect(() => {
    if (refreshInterval && refreshInterval > 0) {
      intervalRef.current = setInterval(fetch, refreshInterval);
      return () => {
        if (intervalRef.current) clearInterval(intervalRef.current);
      };
    }
  }, [refreshInterval, fetch]);

  return { ...state, refetch: fetch };
}
