// frontend/src/utils/api.ts
const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "gv_access";
const REFRESH_KEY = "gv_refresh";

export const tokenStorage = {
  getAccess:   () => localStorage.getItem(TOKEN_KEY),
  getRefresh:  () => localStorage.getItem(REFRESH_KEY),
  setTokens:   (t: { access_token: string; refresh_token: string }) => {
    localStorage.setItem(TOKEN_KEY, t.access_token);
    localStorage.setItem(REFRESH_KEY, t.refresh_token);
  },
  clearTokens: () => { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(REFRESH_KEY); },
};

let _refreshing: Promise<boolean> | null = null;
async function tryRefreshToken(): Promise<boolean> {
  if (_refreshing) return _refreshing;
  _refreshing = (async () => {
    try {
      const refresh = tokenStorage.getRefresh();
      if (!refresh) return false;
      const res = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) { tokenStorage.clearTokens(); return false; }
      tokenStorage.setTokens(await res.json());
      return true;
    } catch { tokenStorage.clearTokens(); return false; }
    finally { _refreshing = null; }
  })();
  return _refreshing;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init.headers as Record<string, string>) };
  const token = tokenStorage.getAccess();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (res.status === 401) {
    const ok = await tryRefreshToken();
    if (ok) { headers["Authorization"] = `Bearer ${tokenStorage.getAccess()}`; res = await fetch(`${BASE_URL}${path}`, { ...init, headers }); }
  }
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const body = await res.json(); msg = body?.detail ?? body?.message ?? msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export const authApi = {
  login:    (p: { email: string; password: string }) => request<{ access_token: string; refresh_token: string; token_type: string }>("/api/v1/auth/login", { method: "POST", body: JSON.stringify(p) }),
  register: (p: { email: string; password: string; full_name: string }) => request<{ id: string }>("/api/v1/auth/register", { method: "POST", body: JSON.stringify(p) }),
  me:       () => request<{ id: string; email: string; full_name: string; role: string; is_active: boolean; created_at: string }>("/api/v1/auth/me"),
  logout:   () => { tokenStorage.clearTokens(); },
};

export const dashboardApi = {
  getStats:  () => request<{ total_trades: number; open_trades: number; win_rate: number; total_pnl: number; daily_pnl: number; equity: number; balance: number; drawdown: number; profit_factor: number; sharpe_ratio: number }>("/api/v1/dashboard/stats"),
  getEquity: (days = 30) => request<Array<{ timestamp: string; equity: number; balance: number }>>(`/api/v1/dashboard/equity?days=${days}`),
};

export const tradesApi = {
  listOpen:   () => request<Array<{ id: string; symbol: string; direction: string; lot_size: number; entry_price: number; stop_loss: number; take_profit: number; pnl?: number; status: string; opened_at: string }>>("/api/v1/trades/open"),
  listClosed: (page = 1, per_page = 20) => request<{ items: Array<{ id: string; symbol: string; direction: string; lot_size: number; entry_price: number; stop_loss: number; take_profit: number; pnl?: number; status: string; opened_at: string; closed_at?: string; close_price?: number }>; total: number; page: number; per_page: number; pages: number }>(`/api/v1/trades/closed?page=${page}&per_page=${per_page}`),
  get:        (id: string) => request<{ id: string; symbol: string }>(`/api/v1/trades/${id}`),
  open:       (p: { symbol: string; direction: string; lot_size: number; stop_loss: number; take_profit: number }) => request<{ id: string }>("/api/v1/trades", { method: "POST", body: JSON.stringify(p) }),
  close:      (id: string) => request<{ id: string }>(`/api/v1/trades/${id}/close`, { method: "POST" }),
  closeAll:   () => request<{ closed: number }>("/api/v1/trades/close-all", { method: "POST" }),
};

export const signalsApi = {
  list:    (status?: string) => request<Array<{ id: string; symbol: string; direction: string; confidence: number; entry_price: number; stop_loss: number; take_profit: number; lot_size: number; status: string; source: string; reasoning?: string; created_at: string }>>(`/api/v1/signals${status ? `?status=${status}` : ""}`),
  get:     (id: string) => request<{ id: string }>(`/api/v1/signals/${id}`),
  approve: (id: string) => request<{ id: string }>(`/api/v1/signals/${id}/approve`, { method: "POST" }),
  reject:  (id: string) => request<{ id: string }>(`/api/v1/signals/${id}/reject`, { method: "POST" }),
};

export const analysisApi = {
  getSMC:         (symbol: string, tf = "H1") => request<{ symbol: string; bias: string; order_blocks: unknown[]; fvg_zones: unknown[]; liquidity_levels: unknown[]; bos_points: unknown[]; confidence: number; updated_at: string }>(`/api/v1/analysis/smc?symbol=${symbol}&timeframe=${tf}`),
  getPriceAction: (symbol: string, tf = "H1") => request<{ symbol: string; trend: string; patterns: unknown[]; rsi: number; macd: { value: number; signal: number; histogram: number }; updated_at: string }>(`/api/v1/analysis/price-action?symbol=${symbol}&timeframe=${tf}`),
  getDecision:    (symbol: string) => request<{ symbol: string; action: string; confidence: number; risk_reward: number; lot_size: number; entry_price: number; stop_loss: number; take_profit: number; reasoning: string; votes: Array<{ agent: string; vote: string; weight: number }>; updated_at: string }>(`/api/v1/analysis/decision?symbol=${symbol}`),
};

export const adminApi = {
  getStats:            () => request<{ total_users: number; active_users: number; total_trades_today: number; system_health: string; kill_switch_active: boolean }>("/api/v1/admin/stats"),
  getSecurityMetrics:  () => request<{ failed_logins_24h: number; blocked_ips: number; active_sessions: number; license_violations: number }>("/api/v1/admin/security"),
  listUsers:           (page = 1) => request<{ items: Array<{ id: string; email: string; full_name: string; role: string; is_active: boolean; created_at: string }>; total: number; page: number; per_page: number; pages: number }>(`/api/v1/admin/users?page=${page}`),
  updateUser:          (id: string, data: Record<string, unknown>) => request<{ id: string }>(`/api/v1/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  activateKillSwitch:  () => request<{ status: string }>("/api/v1/admin/kill-switch/activate",   { method: "POST" }),
  deactivateKillSwitch:() => request<{ status: string }>("/api/v1/admin/kill-switch/deactivate", { method: "POST" }),
};

export const licenseApi = {
  getStatus: () => request<{ is_valid: boolean; license_key: string; expires_at: string; max_accounts: number; active_accounts: number; plan: string }>("/api/v1/license/status"),
  activate:  (key: string) => request<{ is_valid: boolean }>("/api/v1/license/activate", { method: "POST", body: JSON.stringify({ license_key: key }) }),
  heartbeat: () => request<{ ok: boolean }>("/api/v1/license/heartbeat", { method: "POST" }),
};
