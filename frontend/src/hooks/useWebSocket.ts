/**
 * frontend/src/hooks/useWebSocket.ts
 * FIX-E10: WS_URL از config.ts (getWsUrl) — نه VITE_API_URL مستقیم
 * FIX-E11: token از tokenStorage — نه localStorage.getItem مستقیم
 * FIX-E12: mounted guard برای تمام setState
 */
import { useEffect, useRef, useCallback, useState } from "react";
import { tokenStorage } from "@/utils/api";
import { WS_BASE_URL, WS_MAX_RECONNECT } from "@/utils/config";

export type WSMessageType =
  | "TRADE_OPEN" | "TRADE_CLOSE" | "TRADE_UPDATE"
  | "SIGNAL_NEW" | "SIGNAL_EXECUTED" | "SIGNAL_CANCELLED"
  | "RISK_ALERT" | "EQUITY_UPDATE" | "MARKET_DATA"
  | "AUTH_REQUIRED" | "AUTH_OK" | "AUTH_FAIL"
  | "PING" | "PONG" | "ERROR" | "*";

type Handler = (data: unknown) => void;

export interface WSState {
  connected:     boolean;
  reconnecting:  boolean;
  latency:       number;
}

function getWsUrl(): string {
  return `${WS_BASE_URL}/ws`;
}

export function useWebSocket() {
  const ws          = useRef<WebSocket | null>(null);
  const handlers    = useRef<Map<string, Set<Handler>>>(new Map());
  const pingTimer   = useRef<ReturnType<typeof setInterval> | null>(null);
  const pingTs      = useRef<number>(0);
  const retry       = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCount  = useRef(0);
  const mountedRef  = useRef(true);

  const [state, setState] = useState<WSState>({ connected: false, reconnecting: false, latency: 0 });

  const cleanup = useCallback(() => {
    if (pingTimer.current) { clearInterval(pingTimer.current); pingTimer.current = null; }
    if (retry.current)     { clearTimeout(retry.current);      retry.current = null; }
    ws.current?.close();
    ws.current = null;
    retryCount.current = 0;
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (ws.current?.readyState === WebSocket.OPEN) return;
    if (mountedRef.current) setState(s => ({ ...s, reconnecting: retryCount.current > 0 }));

    // FIX-E11: token از tokenStorage — نه localStorage مستقیم
    const token = tokenStorage.getAccess();
    const url   = token ? `${getWsUrl()}?token=${encodeURIComponent(token)}` : getWsUrl();
    const socket = new WebSocket(url);

    socket.onopen = () => {
      if (!mountedRef.current) return;
      retryCount.current = 0;
      setState({ connected: true, reconnecting: false, latency: 0 });
      pingTimer.current = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          pingTs.current = Date.now();
          socket.send(JSON.stringify({ type: "PING" }));
        }
      }, 15_000);
    };

    socket.onmessage = (ev) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(ev.data as string) as { type: string; data?: unknown };
        if (msg.type === "PONG") { setState(s => ({ ...s, latency: Date.now() - pingTs.current })); return; }
        handlers.current.get(msg.type)?.forEach(fn => fn(msg.data));
        handlers.current.get("*")?.forEach(fn => fn(msg));
      } catch { /* ignore */ }
    };

    socket.onclose = () => {
      if (!mountedRef.current) return;
      if (pingTimer.current) { clearInterval(pingTimer.current); pingTimer.current = null; }
      setState(s => ({ ...s, connected: false }));
      const delay = Math.min(1_000 * 2 ** retryCount.current, 30_000);
      retryCount.current += 1;
      if (retryCount.current <= WS_MAX_RECONNECT) {
        retry.current = setTimeout(() => { if (mountedRef.current) connect(); }, delay);
      }
    };

    socket.onerror = () => socket.close();
    ws.current = socket;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => { mountedRef.current = false; cleanup(); };
  }, [connect, cleanup]);

  const on = useCallback((type: WSMessageType | "*", fn: Handler): (() => void) => {
    if (!handlers.current.has(type)) handlers.current.set(type, new Set());
    handlers.current.get(type)!.add(fn);
    return () => handlers.current.get(type)?.delete(fn);
  }, []);

  const send = useCallback((type: string, data: unknown = {}): void => {
    if (ws.current?.readyState === WebSocket.OPEN)
      ws.current.send(JSON.stringify({ type, data }));
  }, []);

  return { ...state, on, send };
}
