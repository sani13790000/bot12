/**
 * frontend/src/utils/api.ts
 * ──────────────────────────────────────────────────────────────
 * Galaxy Vast AI Trading Platform — HTTP API Client
 *
 * ویژگی‌ها:
 *   • refresh خودکار token در خطای 401
 *   • هیچ جزئیات داخلی (stack-trace) به کاربر نشان داده نمی‌شود
 *   • تمام endpoint‌ها زیر /api/v1/ هستند
 *   • adminApi — endpoints مخصوص ADMIN
 *   • licenseApi — مدیریت لایسنس
 */

import { API_BASE_URL } from "./config";
import type {
  ApiResponse,
  Trade,
  Signal,
  DashboardStats,
  EquityPoint,
  PortfolioRisk,
  RiskStatus,
  AnalyticsMetrics,
  AIprediction,
  ModelVersion,
  BacktestResult,
  SecurityMetrics,
  SystemSettings,
  MLWeights,
  User,
  UserSettings,
} from "@/types";

// ── ثابت‌ها ──────────────────────────────────────────────────────────────────
const BASE = `${API_BASE_URL}/api/v1`;
const TOKEN_KEY   = "gv_token";
const REFRESH_KEY = "gv_refresh";

// ── ابزارهای داخلی ───────────────────────────────────────────────────────────

/** هدر Authorization استاندارد */
function authHeader(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** تلاش برای refresh کردن access token با refresh token */
async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_KEY);
      return false;
    }

    const data = await res.json();
    if (data.access_token) {
      localStorage.setItem(TOKEN_KEY, data.access_token);
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

/**
 * درخواست HTTP با refresh خودکار در خطای 401
 * هرگز جزئیات داخلی را نشان نمی‌دهد
 */
async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const url = `${BASE}${path}`;

  const makeRequest = async (): Promise<Response> => {
    return fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...authHeader(),
        ...(options.headers as Record<string, string> | undefined),
      },
    });
  };

  try {
    let res = await makeRequest();

    // اگر 401 بود، یک بار refresh و retry
    if (res.status === 401) {
      const refreshed = await tryRefreshToken();
      if (refreshed) {
        res = await makeRequest();
      } else {
        window.dispatchEvent(new CustomEvent("auth:logout"));
        return { success: false, data: null as unknown as T, error: "نشست منقضی شده است" };
      }
    }

    const json = await res.json();

    if (!res.ok) {
      const safeError =
        res.status >= 500
          ? "خطای سرور — لطفاً دوباره تلاش کنید"
          : json.detail || json.error || json.message || "خطای ناشناخته";
      return { success: false, data: null as unknown as T, error: safeError };
    }

    return { success: true, data: json.data ?? json, ...json };
  } catch (err) {
    const msg = err instanceof TypeError
      ? "خطای شبکه — اتصال اینترنت را بررسی کنید"
      : "خطای ناشناخته";
    return { success: false, data: null as unknown as T, error: msg };
  }
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) }
    ),

  register: (email: string, password: string, full_name?: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>(
      "/auth/register",
      { method: "POST", body: JSON.stringify({ email, password, full_name: full_name ?? "" }) }
    ),

  me: () => request<User>("/auth/me"),

  refresh: (refresh_token: string) =>
    request<{ access_token: string }>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token }),
    }),

  logout: () => request<void>("/auth/logout", { method: "POST" }),
};

// ── Dashboard ─────────────────────────────────────────────────────────────────
export const dashboardApi = {
  getStats:  ()           => request<DashboardStats>("/dashboard/stats"),
  getEquity: (days = 30)  => request<EquityPoint[]>(`/dashboard/equity?days=${days}`),
};

// ── Trades ────────────────────────────────────────────────────────────────────
export const tradesApi = {
  listOpen:   ()               => request<Trade[]>("/trades?status=OPEN"),
  listClosed: (limit = 50)     => request<Trade[]>(`/trades?status=CLOSED&limit=${limit}`),
  list:       (params = "")    => request<Trade[]>(`/trades${params ? "?" + params : ""}`),
  get:        (id: string)     => request<Trade>(`/trades/${id}`),
  close:      (id: string)     => request<Trade>(`/trades/${id}/close`, { method: "POST" }),
  closeAll:   ()               => request<void>("/trades/close-all",    { method: "POST" }),
};

// ── Signals ───────────────────────────────────────────────────────────────────
export const signalsApi = {
  list:    (status?: string) => request<Signal[]>(`/signals${status ? `?status=${status}` : ""}`),
  get:     (id: string)      => request<Signal>(`/signals/${id}`),
  approve: (id: string)      => request<Signal>(`/signals/${id}/approve`, { method: "POST" }),
  reject:  (id: string)      => request<Signal>(`/signals/${id}/reject`,  { method: "POST" }),
};

// ── Portfolio & Risk ──────────────────────────────────────────────────────────
export const portfolioApi = {
  getRisk:   () => request<PortfolioRisk>("/portfolio/risk"),
  getStatus: () => request<RiskStatus>("/risk/status"),
};

// ── Analytics ─────────────────────────────────────────────────────────────────
export const analyticsApi = {
  getMetrics: (period = "month") =>
    request<AnalyticsMetrics>(`/analytics/metrics?period=${period}`),
};

// ── AI & Predictions ─────────────────────────────────────────────────────────
export const aiApi = {
  getPredictions: (symbol?: string) =>
    request<AIprediction[]>(`/ai/predictions${symbol ? `?symbol=${symbol}` : ""}`),
  getModels: () => request<ModelVersion[]>("/ai/models"),
};

// ── Backtest ──────────────────────────────────────────────────────────────────
export const backtestApi = {
  list:  ()                 => request<BacktestResult[]>("/backtest"),
  get:   (id: string)       => request<BacktestResult>(`/backtest/${id}`),
  start: (params: {
    symbol: string;
    start_date: string;
    end_date: string;
    timeframe?: string;
  }) => request<BacktestResult>("/backtest", { method: "POST", body: JSON.stringify(params) }),
};

// ── Users (تنظیمات کاربر) ────────────────────────────────────────────────────
export const usersApi = {
  getSettings:    ()                         => request<UserSettings>("/users/settings"),
  updateSettings: (s: Partial<UserSettings>) =>
    request<UserSettings>("/users/settings", { method: "PATCH", body: JSON.stringify(s) }),
  getProfile:     ()                         => request<User>("/users/profile"),
};

// ── Admin ─────────────────────────────────────────────────────────────────────
export const adminApi = {
  listUsers:   (page = 1, limit = 50) =>
    request<{ users: User[]; total: number }>(`/admin/users?page=${page}&limit=${limit}`),
  getUser:     (id: string)           => request<User>(`/admin/users/${id}`),
  updateUser:  (id: string, data: Partial<User>) =>
    request<User>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteUser:  (id: string)           =>
    request<void>(`/admin/users/${id}`, { method: "DELETE" }),
  toggleUser:  (id: string, active: boolean) =>
    request<User>(`/admin/users/${id}/toggle`, {
      method: "POST",
      body: JSON.stringify({ is_active: active }),
    }),
  getSettings:    ()                             => request<SystemSettings>("/admin/settings"),
  updateSettings: (s: Partial<SystemSettings>)   =>
    request<SystemSettings>("/admin/settings", { method: "PATCH", body: JSON.stringify(s) }),
  getMLWeights:    ()                            => request<MLWeights>("/admin/ml-weights"),
  updateMLWeights: (w: Partial<MLWeights>)       =>
    request<MLWeights>("/admin/ml-weights", { method: "PATCH", body: JSON.stringify(w) }),
  getSecurityMetrics: ()  => request<SecurityMetrics>("/admin/security/metrics"),
  listSecurityEvents: (limit = 50) =>
    request<SecurityMetrics["recent_events"]>(`/admin/security/events?limit=${limit}`),
  killSwitchToggle: (active: boolean, reason?: string) =>
    request<void>("/admin/kill-switch", {
      method: "POST",
      body: JSON.stringify({ active, reason: reason ?? "" }),
    }),
};

// ── License ───────────────────────────────────────────────────────────────────
export const licenseApi = {
  getStatus: () =>
    request<{ status: string; expires_at?: string }>("/license/status"),
  activate: (key: string, device: string) =>
    request<{ ok: boolean }>("/license/activate", {
      method: "POST",
      body: JSON.stringify({ license_key: key, device_id: device }),
    }),
  heartbeat: () =>
    request<{ ok: boolean }>("/license/heartbeat", { method: "POST" }),
  revoke: (key: string) =>
    request<void>("/license/revoke", {
      method: "POST",
      body: JSON.stringify({ license_key: key }),
    }),
};

// ── Analysis ──────────────────────────────────────────────────────────────────
export const analysisApi = {
  getSMC: (symbol: string, timeframe: string) =>
    request<Record<string, unknown>>(`/analysis/smc?symbol=${symbol}&timeframe=${timeframe}`),
  getPriceAction: (symbol: string, timeframe: string) =>
    request<Record<string, unknown>>(`/analysis/price-action?symbol=${symbol}&timeframe=${timeframe}`),
  getDecision: (symbol: string, timeframe: string) =>
    request<Record<string, unknown>>(`/analysis/decision?symbol=${symbol}&timeframe=${timeframe}`),
};
