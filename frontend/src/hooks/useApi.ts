/**
 * هوک‌های API
 *
 * نویسنده: MT5 Trading Team
 */

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';

const API_URL = (import.meta.env?.VITE_API_URL as string | undefined) || 'http://localhost:8000/api';

interface UseApiOptions<T> {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  enabled?: boolean;
  initialData?: T;
}

interface UseApiReturn<T> {
  data: T | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  mutate: (data: T) => void;
}

// هوک عمومی API
export function useApi<T>(options: UseApiOptions<T>): UseApiReturn<T> {
  const { url, method = 'GET', body, enabled = true, initialData } = options;
  const { token } = useAuth();

  const [data, setData] = useState<T | null>(initialData || null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!enabled) {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const headers: HeadersInit = {
        'Content-Type': 'application/json'
      };

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const fetchOptions: RequestInit = {
        method,
        headers
      };

      if (body && method !== 'GET') {
        fetchOptions.body = JSON.stringify(body);
      }

      const response = await fetch(`${API_URL}${url}`, fetchOptions);

      if (!response.ok) {
        if (response.status === 401) {
          localStorage.removeItem('auth_token');
          window.location.href = '/login';
          return;
        }
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();

      if (result.success && result.data !== undefined) {
        setData(result.data);
      } else {
        setData(result);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطای ناشناخته');
    } finally {
      setIsLoading(false);
    }
  }, [url, method, body, token, enabled]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const mutate = useCallback((newData: T) => {
    setData(newData);
  }, []);

  return {
    data,
    isLoading,
    error,
    refetch: fetchData,
    mutate
  };
}

// هوک درخواست POST
export function usePost<T, B = unknown>() {
  const { token } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const post = useCallback(async (url: string, body?: B): Promise<T | null> => {
    setIsLoading(true);
    setError(null);

    try {
      const headers: HeadersInit = {
        'Content-Type': 'application/json'
      };

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${API_URL}${url}`, {
        method: 'POST',
        headers,
        body: body ? JSON.stringify(body) : undefined
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();
      return result.data || result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطای ناشناخته');
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  return { post, isLoading, error };
}

// هوک تحلیل
export function useAnalysis(symbol: string, timeframe: string = 'H1') {
  return useApi({
    url: `/analysis/full?symbol=${symbol}&timeframe=${timeframe}`,
    enabled: !!symbol
  });
}

// هوک معاملات
export function useTrades(filters?: {
  status?: string;
  symbol?: string;
  limit?: number;
}) {
  const params = new URLSearchParams();
  if (filters?.status) params.append('status', filters.status);
  if (filters?.symbol) params.append('symbol', filters.symbol);
  if (filters?.limit) params.append('limit', filters.limit.toString());

  return useApi({
    url: `/trades?${params.toString()}`
  });
}

// هوک معاملات باز
export function useOpenTrades() {
  return useApi({
    url: '/trades/open'
  });
}

// هوک سیگنال‌ها
export function useSignals(filters?: {
  status?: string;
  symbol?: string;
  limit?: number;
}) {
  const params = new URLSearchParams();
  if (filters?.status) params.append('status', filters.status);
  if (filters?.symbol) params.append('symbol', filters.symbol);
  if (filters?.limit) params.append('limit', filters.limit.toString());

  return useApi({
    url: `/signals?${params.toString()}`
  });
}

// هوک سیگنال‌های فعال
export function useActiveSignals() {
  return useApi({
    url: '/signals/active'
  });
}

// هوک گزارش روزانه
export function useDailyReport(date?: string) {
  const params = date ? `?date=${date}` : '';
  return useApi({
    url: `/reports/daily${params}`
  });
}

// هوک گزارش هفتگی
export function useWeeklyReport() {
  return useApi({
    url: '/reports/weekly'
  });
}

// هوک گزارش ماهانه
export function useMonthlyReport(year?: number, month?: number) {
  const params = new URLSearchParams();
  if (year) params.append('year', year.toString());
  if (month) params.append('month', month.toString());

  return useApi({
    url: `/reports/monthly?${params.toString()}`
  });
}

// هوک عملکرد
export function usePerformance(period: 'week' | 'month' | 'year' | 'all' = 'month') {
  return useApi({
    url: `/reports/performance?period=${period}`
  });
}
