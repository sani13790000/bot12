/**
 * frontend/src/utils/api.ts
 * Galaxy Vast Trading - API client
 *
 * P9-FIX-API-1: token refresh on 401 before redirect
 * P9-FIX-API-2: no internal error detail leaked to UI
 * P9-FIX-API-3: adminApi added - all admin endpoints
 * P9-FIX-API-4: licenseApi added
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

let _accessToken: string | null = localStorage.getItem('access_token');
let _refreshToken: string | null = localStorage.getItem('refresh_token');

export function setTokens(access: string, refresh: string): void {
  _accessToken  = access;
  _refreshToken = refresh;
  localStorage.setItem('access_token',  access);
  localStorage.setItem('refresh_token', refresh);
}

export function clearTokens(): void {
  _accessToken  = null;
  _refreshToken = null;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

async function refreshAccessToken(): Promise<boolean> {
  if (!_refreshToken) return false;
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ refresh_token: _refreshToken }),
    });
    if (!res.ok) { clearTokens(); return false; }
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token || _refreshToken);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}

async function apiFetch(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<Response> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401 && retry) {
    const ok = await refreshAccessToken();
    if (ok) return apiFetch(path, options, false);
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired');
  }
  return res;
}

async function apiJSON<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, options);
  if (!res.ok) {
    throw new Error(`API error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// Auth API
export const authApi = {
  login:    (email: string, password: string) =>
    apiJSON<{ access_token: string; refresh_token: string; user: unknown }>(
      '/api/v1/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
    ),
  register: (email: string, password: string, full_name?: string) =>
    apiJSON('/api/v1/auth/register', {
      method: 'POST',
      body:   JSON.stringify({ email, password, full_name }),
    }),
  logout: () =>
    apiFetch('/api/v1/auth/logout', { method: 'POST' }).then(() => clearTokens()),
  me: () => apiJSON('/api/v1/users/me'),
};

// Dashboard API
export const dashboardApi = {
  getStats:       () => apiJSON<Record<string, unknown>>('/api/v1/dashboard/stats'),
  getEquityCurve: (days = 30) => apiJSON(`/api/v1/dashboard/equity-curve?days=${days}`),
  getBotStatus:   () => apiJSON('/api/v1/dashboard/bot-status'),
};

// Signals API
export const signalsApi = {
  getSignals:   (symbol?: string, limit = 50) =>
    apiJSON(`/api/v1/signals?limit=${limit}${symbol ? `&symbol=${symbol}` : ''}`),
  getLatest:    (symbol: string) => apiJSON(`/api/v1/signals/latest?symbol=${symbol}`),
};

// Trades API
export const tradesApi = {
  getOpen:    () => apiJSON('/api/v1/trades/open'),
  getHistory: (page = 1, size = 20) => apiJSON(`/api/v1/trades/history?page=${page}&size=${size}`),
  getStats:   () => apiJSON('/api/v1/trades/stats'),
  closeAll:   () => apiJSON('/api/v1/trades/close-all', { method: 'POST' }),
};

// Risk API
export const riskApi = {
  getStatus:      () => apiJSON('/api/v1/risk/status'),
  triggerKill:    (reason: string) =>
    apiJSON('/api/v1/risk/kill-switch', { method: 'POST', body: JSON.stringify({ reason }) }),
  resetKill:      (reason: string) =>
    apiJSON('/api/v1/risk/kill-switch/reset', { method: 'POST', body: JSON.stringify({ reason }) }),
};

// Analysis API
export const analysisApi = {
  getSMC:        (symbol: string) => apiJSON(`/api/v1/analysis/smc?symbol=${symbol}`),
  getPriceAction:(symbol: string) => apiJSON(`/api/v1/analysis/price-action?symbol=${symbol}`),
  getDecision:   (symbol: string) => apiJSON(`/api/v1/analysis/decision?symbol=${symbol}`),
};

// Admin API
export const adminApi = {
  getUsers:        (page = 1) => apiJSON(`/api/v1/admin/users?page=${page}`),
  getLicenses:     ()         => apiJSON('/api/v1/admin/licenses'),
  getAuditLog:     (limit=50) => apiJSON(`/api/v1/admin/audit?limit=${limit}`),
  killSwitch:      (reason: string) =>
    apiJSON('/api/v1/admin/kill-switch', { method: 'POST', body: JSON.stringify({ reason }) }),
  getSystemHealth: () => apiJSON('/api/v1/admin/health'),
};

// License API
export const licenseApi = {
  getMyLicense:  () => apiJSON('/api/v1/license/my'),
  heartbeat:     () => apiJSON('/api/v1/license/heartbeat', { method: 'POST' }),
  getFeatures:   () => apiJSON('/api/v1/license/features'),
};

export default {
  auth:     authApi,
  dashboard: dashboardApi,
  signals:  signalsApi,
  trades:   tradesApi,
  risk:     riskApi,
  analysis: analysisApi,
  admin:    adminApi,
  license:  licenseApi,
};
