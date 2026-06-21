// frontend/src/utils/api.ts
// FIX-9  login: {telegram_id} -> {email} (422 on every login)
// FIX-10 risk: /risk/status -> /risk/limits (404)
// FIX-11 ai: /api/v1/ai/* -> /api/v1/ai-prediction/* (404)
// FIX-12 trades.close: /trades/{id}/close -> /trades/close/{id} (405)
// FIX-E10 riskApi + analyticsApi ADDED (missing -> RiskPage/AnalyticsPage broken)

import type {
  ApiResponse, DashboardStats, Trade, Signal, PortfolioRisk,
  MLWeights, BacktestResult, SystemSettings, AnalyticsMetrics,
  AIPrediction, ModelVersion, EquityPoint, SecurityMetrics, RiskStatus,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
  const token = localStorage.getItem("gv_token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> ?? {}),
  };
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  } catch {
    return { success: false, data: null as T, error: "\u062e\u0637\u0627\u06cc \u0634\u0628\u06a9\u0647 \u2014 \u0627\u062a\u0635\u0627\u0644 \u0628\u0631\u0631\u0633\u06cc \u0634\u0648\u062f" };
  }
  if (response.status === 401) {
    localStorage.removeItem("gv_token");
    localStorage.removeItem("gv_refresh");
    window.location.href = "/login";
    return { success: false, data: null as T, error: "Unauthorized" };
  }
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Unknown error" }));
    return { success: false, data: null as T, error: err.detail ?? `HTTP ${response.status}` };
  }
  return { success: true, data: await response.json() };
}

export const authApi = {
  login:    (email: string, password: string) =>
    request<{ access_token: string }>("/api/v1/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, full_name: string) =>
    request<{ access_token: string }>("/api/v1/auth/register", {
      method: "POST", body: JSON.stringify({ email, password, full_name }),
    }),
  logout:   () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  refresh:  () => request<{ access_token: string }>("/api/v1/auth/refresh", { method: "POST" }),
  me:       () => request<{ user_id: string; email: string; role: string }>("/api/v1/auth/me"),
};

export const dashboardApi = {
  getStats:       ()        => request<DashboardStats>("/api/v1/dashboard/stats"),
  getEquityCurve: (days=30) => request<{ points: EquityPoint[] }>(`/api/v1/dashboard/equity-curve?days=${days}`),
};

export const tradesApi = {
  listOpen:    ()            => request<Trade[]>("/api/v1/trades/open"),
  listAll:     (limit = 100) => request<Trade[]>(`/api/v1/trades?limit=${limit}`),
  listHistory: ()            => request<Trade[]>("/api/v1/trades?status=closed"),
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
  getModels:   ()               => request<ModelVersion[]>("/api/v1/ai-prediction/models"),
  getFeatures: ()               => request<{ names: string[] }>("/api/v1/ai-prediction/features"),
  trainSymbol: (symbol: string) => request<{ status: string }>(`/api/v1/ai-prediction/train/${symbol}`, { method: "POST" }),
};

export const riskApi = {
  getStatus:  () => request<RiskStatus>("/api/v1/risk/status"),
  getLimits:  () => request<PortfolioRisk>("/api/v1/risk/limits"),
  getEquity:  () => request<{ equity: number; balance: number; margin_level: number }>("/api/v1/risk/equity/state"),
  getWeights: () => request<MLWeights>("/api/v1/risk/weights"),
};

export const analyticsApi = {
  getMetrics:         (days = 30) => request<AnalyticsMetrics>(`/api/v1/analytics/performance?days=${days}`),
  getSecurityReport:  (days = 30) => request<{ report_id: string; score: number; total_attacks: number }>(`/api/v1/analytics/security/report?days=${days}`),
  getSecurityMetrics: ()          => request<SecurityMetrics>("/api/v1/analytics/security/metrics"),
};

export const backtestApi = {
  run:       (params: Record<string, unknown>) =>
    request<{ job_id: string }>("/api/v1/backtest/run", { method: "POST", body: JSON.stringify(params) }),
  getResult: (jobId: string)  => request<BacktestResult>(`/api/v1/backtest/result/${jobId}`),
  list:      ()               => request<BacktestResult[]>("/api/v1/backtest/list"),
};

export const settingsApi = {
  get:    ()                           => request<SystemSettings>("/api/v1/users/settings"),
  update: (s: Partial<SystemSettings>) => request<SystemSettings>("/api/v1/users/settings", { method: "PATCH", body: JSON.stringify(s) }),
};
