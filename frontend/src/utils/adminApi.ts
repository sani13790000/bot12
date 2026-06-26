// frontend/src/utils/adminApi.ts
// P9-FEAT4: Admin API client -- admin-only, role-gated
import type { ApiResponse } from "@/types";
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
async function req<T>(path: string, opts: RequestInit = {}): Promise<ApiResponse<T>> {
  const token = localStorage.getItem("gv_token");
  const headers: Record<string, string> = { "Caturent-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(opts.headers as Record<string, string> ?? {}) };
  let res: Response; try { res = await fetch(`${BASE}${path}`, { ...opts, headers }); } catch { return { success: false, data: null as T, error: "خسЉY�ع شч�d" }; }
  if (res.status === 403) return { success: false, data: null as T, error: "داٸذ��ع ؍щذمщر� я`�� admin لاڎم щX�ت" };
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: `HTTP ${res.status}` })); return { success: false, data: null as T, error: e.detail || `HTTP ${res.status}` }; }
  return { success: true, data: await res.json() };
}
export interface AdminUser { id: string; email: string; full_name: string | null; role: string; is_active: boolean; created_at: string; last_login: string | null; }
export interface AdminLicense { id: string; user_email: string; plan: string; state: string; devices_active: number; device_limit: number; expires_at: string; created_at: string; }
export interface AdminDevice { device_id: string; user_email: string; ip_address: string | null; user_agent: string | null; last_heartbeat: string; registered_at: string; }
export interface AdminLog { ts: string; level: string; event: string; actor: string | null; ip: string | null; detail: string | null; }
export const adminApi = {
  listUsers: () => req<AdminUser[]>("/api/v1/admin/users"),
  blockUser: (id: string) => req<void>( `/api/v1/admin/users/${id}/block`, { method: "POST" }),
  unblockUser: (id: string) => req<void>(`/api/v1/admin/users/${id}/unblock`, { method: "POST" }),
  changeRole: (id: string, role: string) => req<void>(`/api/v1/admin/users/${id}/role`, { method: "PATCH", body: JSON.stringify({ role }) }),
  listLicenses: () => req<AdminLicense[]>("/api/v1/admin/licenses"),
  suspendLicense: (id: string) => req<void>(`/api/v1/admin/licenses/${id}/suspend`, { method: "POST" }),
  revokeLicense: (id: string) => req<void>(`/api/v1/admin/licenses/${id}/revoke`, { method: "POST" }),
  extendLicense: (id: string, days: number) => req<void>(`/api/v1/admin/licenses/${id}/extend`, { method: "POST", body: JSON.stringify({ days }) }),
  listDevices: () => req<AdminDevice[]>("/api/v1/admin/devices"),
  revokeDevice: (deviceId: string) => req<void>("/api/v1/admin/devices/revoke", { method: "POST", body: JSON.stringify({ device_id: deviceId }) }),
  listLogs: (level?: string) => req<AdminLog[]>(`/api/v1/admin/logs${level ? `?level=${level}` : ""}`),
  triggerKillSwitch: (reason: string) => req<void>("/api/v1/admin/kill-switch", { method: "POST", body: JSON.stringify({ reason }) }),
  resetKillSwitch: (adminToken: string) => req<void>("/api/v1/admin/kill-switch/reset", { method: "POST", body: JSON.stringify({ admin_token: adminToken }) }),
};
