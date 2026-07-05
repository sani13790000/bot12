/**
 * frontend/src/utils/config.ts
 * FIX-E5: تمام URL‌ها از env var — نه hardcode
 * FIX-E6: validation در startup
 */
const _env = import.meta.env as Record<string, string | undefined>;

export const API_BASE_URL: string =
  (_env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export const WS_BASE_URL: string = (() => {
  const ws = _env.VITE_WS_URL;
  if (ws) return ws.replace(/\/$/, "");
  return API_BASE_URL.replace(/^https/, "wss").replace(/^http/, "ws");
})();

export const APP_ENV: string  = _env.VITE_APP_ENV ?? "development";
export const IS_PROD: boolean = APP_ENV === "production";
export const IS_DEV:  boolean = !IS_PROD;

export const ENABLE_WS:            boolean = _env.VITE_ENABLE_WS            !== "false";
export const ENABLE_NOTIFICATIONS: boolean = _env.VITE_ENABLE_NOTIFICATIONS  !== "false";
export const ENABLE_DARK_MODE:     boolean = _env.VITE_ENABLE_DARK_MODE      !== "false";

export const API_TIMEOUT_MS:   number = Number(_env.VITE_API_TIMEOUT_MS)   || 15_000;
export const WS_MAX_RECONNECT: number = Number(_env.VITE_WS_MAX_RECONNECT) || 10;
export const POLL_INTERVAL_MS: number = Number(_env.VITE_POLL_INTERVAL_MS) || 10_000;

if (IS_DEV && !_env.VITE_API_URL) {
  // eslint-disable-next-line no-console
  console.warn(
    "[config] VITE_API_URL not set — falling back to http://localhost:8000.\n" +
    "Copy frontend/.env.local.example → .env.local"
  );
}
