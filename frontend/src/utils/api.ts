/**
 * frontend/src/utils/api.ts
 * FIX-E1: BASE_URL از VITE_API_URL env var — نه localhost hardcode
 * FIX-E2: 401 → token refresh → retry یک‌بار
 * FIX-E3: tokenStorage متمرکز
 */
import type { User, LoginPayload, RegisterPayload, AuthTokens } from "@/types";

const _BASE = (import.meta.env?.VITE_API_URL as string | undefined)
  ?? "http://localhost:8000";
export const API_BASE_URL = _BASE.replace(/\/$/, "");

const _K_ACCESS  = "gv_token";
const _K_REFRESH = "gv_refresh";

export const tokenStorage = {
  getAccess:   () => localStorage.getItem(_K_ACCESS),
  getRefresh:  () => localStorage.getItem(_K_REFRESH),
  setTokens:   (t: AuthTokens) => {
    localStorage.setItem(_K_ACCESS, t.access_token);
    if (t.refresh_token) localStorage.setItem(_K_REFRESH, t.refresh_token);
  },
  clearTokens: () => {
    localStorage.removeItem(_K_ACCESS);
    localStorage.removeItem(_K_REFRESH);
  },
};

let _refreshing: Promise<string | null> | null = null;

async function _refreshAccessToken(): Promise<string | null> {
  const refresh = tokenStorage.getRefresh();
  if (!refresh) return null;
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) { tokenStorage.clearTokens(); return null; }
    const data: AuthTokens = await res.json();
    tokenStorage.setTokens(data);
    return data.access_token;
  } catch {
    tokenStorage.clearTokens();
    return null;
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {},
  _retry = true,
): Promise<T> {
  const token   = tokenStorage.getAccess();
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (res.status === 401 && _retry) {
    if (!_refreshing)
      _refreshing = _refreshAccessToken().finally(() => { _refreshing = null; });
    const newToken = await _refreshing;
    if (newToken) return apiFetch<T>(path, options, false);
    tokenStorage.clearTokens();
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const e = await res.json(); msg = e?.detail ?? e?.message ?? msg; }
    catch { /* ignore */ }
    throw new Error(msg);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const authApi = {
  login:    (p: LoginPayload)    => apiFetch<AuthTokens>("/api/v1/auth/login",   { method: "POST", body: JSON.stringify(p) }),
  register: (p: RegisterPayload) => apiFetch<void>("/api/v1/auth/register", { method: "POST", body: JSON.stringify(p) }),
  me:       ()                   => apiFetch<User>("/api/v1/auth/me"),
  logout:   ()                   => apiFetch<void>("/api/v1/auth/logout",   { method: "POST" }).catch(() => {}),
  refresh:  (token: string)      => apiFetch<AuthTokens>("/api/v1/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: token }) }),
};

export const api = {
  get:    <T>(path: string)                => apiFetch<T>(path),
  post:   <T>(path: string, body: unknown) => apiFetch<T>(path, { method: "POST",   body: JSON.stringify(body) }),
  put:    <T>(path: string, body: unknown) => apiFetch<T>(path, { method: "PUT",    body: JSON.stringify(body) }),
  patch:  <T>(path: string, body: unknown) => apiFetch<T>(path, { method: "PATCH",  body: JSON.stringify(body) }),
  delete: <T>(path: string)               => apiFetch<T>(path, { method: "DELETE" }),
};
