// frontend/src/hooks/useApi.ts
import { useState, useEffect, useCallback, useRef } from "react";

interface ApiState<T> {
  data:      T | null;
  isLoading: boolean;
  error:     string | null;
  refetch:   () => void;
}

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): ApiState<T> {
  const [data,      setData]      = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error,     setError]     = useState<string | null>(null);
  const counterRef = useRef(0);

  const run = useCallback(async () => {
    const id = ++counterRef.current;
    setIsLoading(true); setError(null);
    try {
      const result = await fetcher();
      if (id === counterRef.current) setData(result);
    } catch (e) {
      if (id === counterRef.current)
        setError(e instanceof Error ? e.message : "خطای ناشناخته");
    } finally {
      if (id === counterRef.current) setIsLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => { run(); }, [run]);
  return { data, isLoading, error, refetch: run };
}

export function usePoll<T>(fetcher: () => Promise<T>, intervalMs: number, deps: unknown[] = []): ApiState<T> {
  const state = useApi<T>(fetcher, deps);
  useEffect(() => {
    const t = setInterval(state.refetch, intervalMs);
    return () => clearInterval(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);
  return state;
}
