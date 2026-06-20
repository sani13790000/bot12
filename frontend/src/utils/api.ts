// Galaxy Vast AI Trading Platform -- Typed API Client v4
//
// FIX-9  login: {telegram_id,password} -> {email,password} (422 on every login)
// FIX-10 risk: /risk/status -> /risk/limits (404)
// FIX-11 ai: /api/v1/ai/* -> /api/v1/ai-prediction/* (404)
// FIX-12 trades.close: /trades/{id}/close -> /trades/close/{id} (405)

import type {
  ApiResponse, DashboardStats, Trade, Signal, PortfolioRisk,
  MLWeights, BacktestResult, SystemSettings, AnalyticsMetrics,
  AIPrediction, ModelVersion, EquityPoint,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
  const token = localStorage.getItem("gv_token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> ?? {}),
  };
  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (response.status === 401) {
    localStorage.removeItem("gv_token");
    window.location.href = "/login";
    return { success: false, data: null as T, error: "Unauthorized" };
  }
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Unknown error" }));
    return { success: false, data: null as T, error: err.detail ?? "Request failed" };
  }
  return { success: true, data: await response.json() };
}

export const authApi = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/api/v1/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, full_name: string) =>
    request<{ access_token: string }>("/api/v1/auth/register", {
      method: "POST", body: JSON.stringify({ email, password, full_name }),
    }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  refresh: () => request<{ access_token: string }>("/api/v1/auth/refresh", { method: "POST" }),
  me: () => request<{ user_id: string; role: string }>("/api/v1/auth/me"),
};

export const dashboardApi = {
  getStats: () => request<DashboardStats>("/api/v1/dashboard/stats"),
  getEquityCurve: (days = 30) =>
    request<{ points: EquityPoint[] }>(`/api/v1/dashboard/equity-curve?days=${days}`),
};

export const tradesApi = {
  listOpen:    ()            => request<Trade[]>("/api/v1/trades/open"),
  listAll:     (limit = 100) => request<Trade[]>(`/api/v1/trades?limit=${limit}`),
  listHistory: (limit = 200) => request<Trade[]>("/api/v1/trades?status=closed"),
  close:       (id: string)  => request<void>(`/api/v1/trades/close/${id}`, { method: "POST" }),
  closeAll:    ()            => request<void>("/api/v1/trades/close-all", { method: "POST" }),
};

export const signalsApi = {
  list:    (status?: string) => request<Signal[]>(`/api/v1/signals${status ? `?status=${status}` : ""}`),
  execute: (id: string)      => request<void>(`/api/v1/signals/${id}/execute`, { method: "POST" }),
  cancel:  (id: string)      => request<void>(`/api/v1/signals/${id}/cancel`,  { method: "POST" }),
};

export const aiApi = {
  predict:      (payload: Record<string, unknown>) =>
    request<AIPrediction>("/api/v1/ai-prediction/predict", { method: "POST", body: JSON.stringify(payload) }),
  batchPredict: (payloads: Record<string, unknown>[]) =>
    request<AIPrediction[]>("/api/v1/ai-prediction/batch-predict", { method: "POST", body: JSON.stringify(payloads) }),
  getModels:    ()               => request<ModelVersion[]>("/api/v1/ai-prediction/models"),
  getFeatures:  ()               => request<{ names: string[] }>("/api/v1/ai-prediction/features"),
  trainSymbol:  (symbol: string) =>
    request<{ status: string }>(`/api/v1/ai-prediction/train/${symbol}`, { method: "POST" }),
};

export const riskApi = {
  getLimits:    () => request<PortfolioRisk>("/api/v1/risk/limits"),
  calculate:    (body: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/v1/risk/calculate", { method: "POST", body: JSON.stringify(body) }),
  positionSize: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/v1/risk/position-size", { method: "POST", body: JSON.stringify(body) }),
};

export const analysisApi = {
  analyze: (symbol: string, timeframe = "H1") =>
    request<Record<string, unknown>>(`/api/v1/analysis/analyze?symbol=${symbol}&timeframe=${timeframe}`),
};

export const analyticsApi = {
  getMetrics:           () => request<AnalyticsMetrics>("/api/v1/analytics/metrics"),
  getSecurityMetrics:   () => request<Record<string, unknown>>("/api/v1/analytics/security/metrics"),
  getSecurityDashboard: () => request<Record<string, unknown>>("/api/v1/analytics/security/dashboard"),
};

export const mlApi = {
  getWeights:    () => request<MLWeights>("/api/v1/intelligence/weights"),
  updateWeights: (weights: Partial<MLWeights>) =>
    request<void>("/api/v1/intelligence/weights", { method: "POST", body: JSON.stringify(weights) }),
};

export const backtestApi = {
  run:        (config: Record<string, unknown>) =>
    request<BacktestResult>("/api/v1/backtest/run", { method: "POST", body: JSON.stringify(config) }),
  getSymbols: () => request<{ symbols: string[] }>("/api/v1/backtest/symbols"),
};

export const settingsApi = {
  get:    () => request<SystemSettings>("/api/v1/users/settings"),
  update: (settings: Partial<SystemSettings>) =>
    request<void>("/api/v1/users/settings", { method: "PUT", body: JSON.stringify(settings) }),
};

export const reportsApi = {
  list:     () => request<Record<string, unknown>[]>("/api/v1/reports"),
  generate: (days = 30) =>
    request<Record<string, unknown>>("/api/v1/analytics/security/report", {
      method: "POST", body: JSON.stringify({ days }),
    }),
};
