// ════════════════════════════════════════════════════════════════
// Galaxy Vast AI Trading Platform — Typed API Client v3
// ════════════════════════════════════════════════════════════════
import type {
  ApiResponse, DashboardStats, Trade, Signal, PortfolioRisk,
  MLWeights, BacktestResult, SystemSettings, AnalyticsMetrics,
  BreakdownItem, AIPrediction, ModelVersion, EquityPoint,
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
  const json = await response.json();
  return { success: true, data: json };
}

// ── Auth ──────────────────────────────────────────────────────
export const authApi = {
  login: (telegram_id: string, password: string) =>
    request<{ access_token: string }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ telegram_id, password }),
    }),
};

// ── Dashboard ─────────────────────────────────────────────────
export const dashboardApi = {
  getStats: () => request<DashboardStats>("/api/v1/dashboard/stats"),
  getEquityCurve: (days = 30) =>
    request<{ points: EquityPoint[] }>(`/api/v1/dashboard/equity-curve?days=${days}`),
};

// ── Live Trades ───────────────────────────────────────────────
export const tradesApi = {
  listOpen:    ()           => request<Trade[]>("/api/v1/trades?status=OPEN"),
  listAll:     (limit = 100) => request<Trade[]>(`/api/v1/trades?limit=${limit}`),
  listHistory: (limit = 200) => request<Trade[]>("/api/v1/trades?status=CLOSED"),
  close:       (id: string) => request<void>(`/api/v1/trades/${id}/close`,  { method: "POST" }),
  closeAll:    ()           => request<void>("/api/v1/trades/close-all",     { method: "POST" }),
};

// ── Signals ───────────────────────────────────────────────────
export const signalsApi = {
  list:    (status?: string) => request<Signal[]>(`/api/v1/signals${status ? `?status=${status}` : ""}`),
  execute: (id: string)      => request<void>(`/api/v1/signals/${id}/execute`, { method: "POST" }),
  cancel:  (id: string)      => request<void>(`/api/v1/signals/${id}/cancel`,  { method: "POST" }),
};

// ── AI Predictions ────────────────────────────────────────────
export const aiApi = {
  predict:       (payload: Record<string, unknown>) =>
    request<AIPrediction>("/api/v1/ai/predict", { method: "POST", body: JSON.stringify(payload) }),
  batchPredict:  (payloads: Record<string, unknown>[]) =>
    request<AIPrediction[]>("/api/v1/ai/batch-predict", { method: "POST", body: JSON.stringify(payloads) }),
  getModels:     ()           => request<ModelVersion[]>("/api/v1/ai/models"),
  getFeatures:   ()           => request<{ names: string[] }>("/api/v1/ai/feature-names"),
  trainSymbol:   (symbol: string) =>
    request<{ status: string }>(`/api/v1/ai/train/${symbol}`, { method: "POST" }),
};

// ── Risk ──────────────────────────────────────────────────────
export const riskApi = {
  getPortfolio: () => request<PortfolioRisk>("/api/v1/risk/status"),
  getEquity:    () => request<{ drawdown_pct: number; halt_active: boolean }>("/api/v1/risk/equity/state"),
  resumeHalt:   () => request<void>("/api/v1/risk/equity/resume", { method: "POST" }),
  resetDaily:   () => request<void>("/api/v1/risk/reset/daily",   { method: "POST" }),
};

// ── Analytics ─────────────────────────────────────────────────
export const analyticsApi = {
  getMetrics:    ()          => request<AnalyticsMetrics>("/api/v1/analytics/metrics"),
  getSummary:    ()          => request<Record<string, number>>("/api/v1/analytics/summary"),
  getEquity:     ()          => request<{ points: EquityPoint[] }>("/api/v1/analytics/equity-curve"),
  getDrawdown:   ()          => request<{ points: EquityPoint[] }>("/api/v1/analytics/drawdown"),
  getBySymbol:   ()          => request<BreakdownItem[]>("/api/v1/analytics/breakdown/symbol"),
  getBySession:  ()          => request<BreakdownItem[]>("/api/v1/analytics/breakdown/session"),
  compare:       (period: string) => request<Record<string, unknown>>(`/api/v1/analytics/compare?period=${period}`),
  getReport:     ()          => request<Record<string, unknown>>("/api/v1/analytics/report/json"),
};

// ── Model Performance ─────────────────────────────────────────
export const modelApi = {
  getVersions:  (symbol: string)   => request<ModelVersion[]>(`/api/v1/self-learning/models/${symbol}`),
  compare:      (symbol: string)   => request<Record<string, unknown>>(`/api/v1/self-learning/models/${symbol}/compare`),
  retrain:      (symbol: string)   => request<{ status: string }>("/api/v1/self-learning/retrain", { method: "POST", body: JSON.stringify({ symbol }) }),
  rollback:     (symbol: string)   => request<{ status: string }>("/api/v1/self-learning/rollback", { method: "POST", body: JSON.stringify({ symbol }) }),
  getStatus:    ()                 => request<Record<string, unknown>>("/api/v1/self-learning/status"),
  getWeights:   ()                 => request<MLWeights>("/api/v1/intelligence/weights"),
  runLearning:  ()                 => request<{ status: string }>("/api/v1/intelligence/run-learning", { method: "POST" }),
};

// ── Bot Control ───────────────────────────────────────────────
export const botApi = {
  start:  () => request<void>("/api/v1/bot/start",  { method: "POST" }),
  stop:   () => request<void>("/api/v1/bot/stop",   { method: "POST" }),
  pause:  () => request<void>("/api/v1/bot/pause",  { method: "POST" }),
  resume: () => request<void>("/api/v1/bot/resume", { method: "POST" }),
};

// ── Settings ──────────────────────────────────────────────────
export const settingsApi = {
  get:    ()                              => request<SystemSettings>("/api/v1/settings"),
  update: (data: Partial<SystemSettings>) =>
    request<SystemSettings>("/api/v1/settings", { method: "PATCH", body: JSON.stringify(data) }),
};

// ── Research ──────────────────────────────────────────────────
export const researchApi = {
  runBacktest: (payload: Record<string, unknown>) =>
    request<BacktestResult>("/api/v1/research/backtest", { method: "POST", body: JSON.stringify(payload) }),
  runMonteCarlo: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/v1/research/monte-carlo", { method: "POST", body: JSON.stringify(payload) }),
  walkForward: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/v1/research/walk-forward", { method: "POST", body: JSON.stringify(payload) }),
};
