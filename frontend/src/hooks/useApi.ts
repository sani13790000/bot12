// frontend/src/hooks/useApi.ts
// FIX-FE6: infinite loop — fetcher ref instability
//   قبل: useCallback([fetcher]) → fetcher هر render عوض → infinite re-fetch
//   بعد: fetcherRef pattern — no deps روی execute

import { useState, useEffect, useCallback, useRef } from "react";

export interface UseApiOptions {
  autoFetch?: boolean;
  refreshInterval?: number;
}

export interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  lastFetched: Date | null;
}

export function useApi<T>(
  fetcher: () => Promise<{ success: boolean; data: T; error?: string }>,
  options: UseApiOptions = {},
) {
  const { autoFetch = true, refreshInterval } = options;

  const [state, setState] = useState<UseApiState<T>>({
    data: null, loading: false, error: null, lastFetched: null,
  });

  const fetcherRef  = useRef(fetcher);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef  = useRef(true);
  fetcherRef.current = fetcher;

  const execute = useCallback(async () => {
    if (!mountedRef.current) return;
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
      setState(s => ({ ...s, loading: false, error: String(e) }));
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (autoFetch) execute();
    return () => { mountedRef.current = false; };
  }, [autoFetch, execute]);

  useEffect(() => {
    if (refreshInterval && refreshInterval > 0) {
      intervalRef.current = setInterval(execute, refreshInterval);
      return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
    }
  }, [refreshInterval, execute]);

  return { ...state, refetch: execute };
}
