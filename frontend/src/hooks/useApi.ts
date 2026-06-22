import { useState, useEffect, useCallback, useRef } from "react";

/**
 * FIX-FE10: infinite loop — fetcher changed every render → useEffect re-ran
 * FIX-FE11: refreshInterval memory leak on unmount
 * FIX-FE12: 'fetch' shadowed global fetch() — renamed to 'execute'
 */

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
  options: UseApiOptions = {},
) {
  const { autoFetch = true, refreshInterval } = options;

  const fetcherRef = useRef(fetcher);
  useEffect(() => { fetcherRef.current = fetcher; });

  const [state, setState] = useState<UseApiState<T>>({
    data: null, loading: false, error: null, lastFetched: null,
  });

  const execute = useCallback(async () => {
    setState(s => ({ ...s, loading: true, error: null }));
    try {
      const res = await fetcherRef.current();
      if (res.success) {
        setState({ data: res.data, loading: false, error: null, lastFetched: new Date() });
      } else {
        setState(s => ({ ...s, loading: false, error: res.error ?? "خطای ناشناخته" }));
      }
    } catch (e) {
      setState(s => ({ ...s, loading: false, error: String(e) }));
    }
  }, []);

  const didMount = useRef(false);
  useEffect(() => {
    if (autoFetch && !didMount.current) {
      didMount.current = true;
      void execute();
    }
  }, [autoFetch, execute]);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (refreshInterval && refreshInterval > 0) {
      intervalRef.current = setInterval(() => void execute(), refreshInterval);
      return () => {
        if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
      };
    }
  }, [refreshInterval, execute]);

  return { ...state, refetch: execute };
}
