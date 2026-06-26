// frontend/src/utils/licenseApi.ts
// P9-FEAT-3: License API client -- customer-facing
import type { ApiResponse } from "@/types";
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
async function req<T>(path: string, opts: RequestInit = {}): Promise<ApiResponse<T>> {
  const token = localStorage.getItem("gv_token");
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(opts.headers as Record<string, string> ?? {}) };
  let res: Response; try { res = await fetch(`${BASE}${path}`, { ...opts, headers }); } catch { return { success: false, data: null as T, error: "خسЉY�ع شч�d" }; }
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: `HTTP ${res.status}` })); return { success: false, data: null as T, error: e.detail || `HTTP ${res.status}` }; }
  return { success: true, data: await res.json() };
}
export interface LicenseStatus { state: string; plan: string; expires_at: string; devices_active: number; device_limit: number; features: string[]; heartbeat_due: string | null; }
export const licenseApi = {
  getStatus: () => req<LicenseStatus>("/api/v1/license/status"),
  registerDevice: (clientId: string) => req<{ device_id: string; success: boolean }>("/api/v1/license/device/register", { method: "POST", body: JSON.stringify({ client_id: clientId }) }),
  heartbeat: (deviceId: string, nonce: string, clientSig: string) => req<any>("/api/v1/license/heartbeat", { method: "POST", body: JSON.stringify({ device_id: deviceId, nonce, client_sig: clientSig, ts: Date.now() / 1000 }) }),
  deactivate: (deviceId: string) => req<{ success: boolean }>("/api/v1/license/device/deactivate", { method: "POST", body: JSON.stringify({ device_id: deviceId }) }),
};
