// ============================================================
// Galaxy Vast — Typed API Client
// All calls go through this single module — never fetch() directly
// ============================================================

import type {
  ApiResponse,
  DashboardStats,
  Trade,
  Signal,
  PortfolioRisk,
  MLWeights,
  BacktestResult,
  SystemSettings,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// ── Core fetch wrapper ───────────────────────────────────────
async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
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

// ── Auth ─────────────────────────────────────────────────────
export const authApi = {
  login: (telegram_id: string, password: string) =>
    request<{ access_token: string }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ telegram_id, password }),
    }),
};

// ── Dashboard ────────────────────────────────────────────────
export const dashboardApi = {
  getStats: () => request<DashboardStats>("/api/v1/dashboard/stats"),
  getEquityCurve: (days = 30) =>
    request<{ points: { date: string; equity: number; balance: number; drawdown: number }[] }>(
      `/api/v1/dashboard/equity-curve?days=${days}`
    ),
};

// ── Trades ───────────────────────────────────────────────────
export const tradesApi = {
  list: (status?: string) =>
    request<Trade[]>(`/api/v1/trades${status ? `?status=${status}` : ""}`),
  closeAll: () => request<void>("/api/v1/trades/close-all", { method: "POST" }),
  close: (id: string) =>
    request<void>(`/api/v1/trades/${id}/close`, { method: "POST" }),
};

// ── Signals ──────────────────────────────────────────────────
export const signalsApi = {
  list: (status?: string) =>
    request<Signal[]>(`/api/v1/signals${status ? `?status=${status}` : ""}`),
  execute: (id: string) =>
    request<void>(`/api/v1/signals/${id}/execute`, { method: "POST" }),
  cancel: (id: string) =>
    request<void>(`/api/v1/signals/${id}/cancel`, { method: "POST" }),
};

// ── Portfolio Risk ────────────────────────────────────────────
export const riskApi = {
  getPortfolio: () => request<PortfolioRisk>("/api/v1/risk/portfolio"),
};

// ── Intelligence / ML ─────────────────────────────────────────
export const intelligenceApi = {
  getWeights: () => request<MLWeights>("/api/v1/intelligence/weights"),
  runLearning: () =>
    request<{ status: string }>("/api/v1/intelligence/run-learning", {
      method: "POST",
    }),
  getMemoryStats: () =>
    request<{ total: number; wins: number; losses: number; avg_rr: number }>(
      "/api/v1/intelligence/memory/stats"
    ),
};

// ── Bot Control ──────────────────────────────────────────────
export const botApi = {
  start:  () => request<void>("/api/v1/bot/start",  { method: "POST" }),
  stop:   () => request<void>("/api/v1/bot/stop",   { method: "POST" }),
  pause:  () => request<void>("/api/v1/bot/pause",  { method: "POST" }),
  resume: () => request<void>("/api/v1/bot/resume", { method: "POST" }),
};

// ── Settings ─────────────────────────────────────────────────
export const settingsApi = {
  get: () => request<SystemSettings>("/api/v1/settings"),
  update: (data: Partial<SystemSettings>) =>
    request<SystemSettings>("/api/v1/settings", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};

// ── Research ─────────────────────────────────────────────────
export const researchApi = {
  runBacktest: (payload: Record<string, unknown>) =>
    request<BacktestResult>("/api/v1/research/backtest", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
